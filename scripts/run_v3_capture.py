"""Capture and resample prospective public Kraken L2 sessions into unique run folders.

The defaults target BTC/USDT, while the frozen V3 capture manifest is BTC/USD;
these outputs must not be called a confirmatory V3 replication without resolving
that instrument mismatch. No output is written to the historical V3 directories.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PYTHON_EXE = sys.executable


def log(msg: str) -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{now}] {msg}", flush=True)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run_cmd(cmd: list[str], desc: str) -> tuple[bool, str, str]:
    log(f"Ejecutando: {desc}...")
    start = time.monotonic()
    proc = subprocess.run(cmd, cwd=str(PROJECT_ROOT), capture_output=True, text=True)
    elapsed = time.monotonic() - start
    if proc.returncode != 0:
        log(f"ERROR en {desc} ({elapsed:.1f}s, código {proc.returncode})")
        return False, proc.stdout, proc.stderr
    log(f"Éxito: {desc} ({elapsed:.1f}s)")
    return True, proc.stdout, proc.stderr


def capture_session(session_idx: int, symbol: str, depth: int, duration_sec: int, out_dir: Path) -> dict:
    session_id = f"v3_prospective_session_{session_idx:02d}_{symbol.replace('/', '_').lower()}_l2"
    raw_path = out_dir / f"{session_id}.parquet"
    resampled_path = out_dir / f"{session_id}_1s.parquet"
    raw_manifest = raw_path.with_suffix(raw_path.suffix + ".manifest.json")

    # 1. Captura en vivo
    cap_cmd = [
        PYTHON_EXE,
        str(PROJECT_ROOT / "scripts" / "capture_kraken_l2.py"),
        "--symbol", symbol,
        "--depth", str(depth),
        "--seconds", str(duration_sec),
        "--output", str(raw_path),
    ]
    ok, out, err = run_cmd(cap_cmd, f"Captura {session_id} ({duration_sec}s)")
    if not ok:
        raise RuntimeError(f"Fallo en captura de sesión {session_idx}: {err}")

    raw_sha = sha256_file(raw_path)
    cap_meta = json.loads(raw_manifest.read_text(encoding="utf-8")) if raw_manifest.exists() else {}

    # 2. Resampleo causal a 1.0 s
    res_cmd = [
        PYTHON_EXE,
        str(PROJECT_ROOT / "scripts" / "resample_l2_1s.py"),
        "--input", str(raw_path),
        "--output", str(resampled_path),
        "--gap-threshold", "3.0",
    ]
    ok, out, err = run_cmd(res_cmd, f"Resampleo {session_id} a 1s")
    if not ok:
        raise RuntimeError(f"Fallo en resampleo de sesión {session_idx}: {err}")

    resampled_sha = sha256_file(resampled_path)
    res_manifest = resampled_path.with_suffix(resampled_path.suffix + ".manifest.json")

    # 3. Auditoría de calidad de la sesión
    import pandas as pd
    from navier_lab.schema import STATE_GAP_DISCONTINUITY

    df_1s = pd.read_parquet(resampled_path)
    total_sec = len(df_1s)
    gap_sec = int((df_1s["state_source"] == STATE_GAP_DISCONTINUITY).sum())
    gap_pct = (gap_sec / total_sec * 100.0) if total_sec else 0.0

    counters = cap_meta.get("adapter_counters", {})
    crc_failures = counters.get("checksum_failures", 0)
    reconnects = counters.get("reconnects", 0)

    invalidation_reasons = []
    if crc_failures > 0:
        invalidation_reasons.append(f"CRC32 mismatch ({crc_failures})")
    if reconnects > 2:
        invalidation_reasons.append(f"Reconexiones excesivas ({reconnects})")
    if gap_pct > 3.0:
        invalidation_reasons.append(f"Gaps excesivos ({gap_pct:.2f}%)")

    status = "VALID" if not invalidation_reasons else "INVALID"

    return {
        "session_index": session_idx,
        "session_id": session_id,
        "symbol": symbol,
        "depth": depth,
        "started_at_utc": cap_meta.get("started_at_utc"),
        "ended_at_utc": cap_meta.get("ended_at_utc"),
        "elapsed_seconds": cap_meta.get("elapsed_seconds"),
        "raw_file": raw_path.name,
        "raw_sha256": raw_sha,
        "resampled_file": resampled_path.name,
        "resampled_sha256": resampled_sha,
        "total_seconds_1s": total_sec,
        "gap_seconds": gap_sec,
        "gap_pct": round(gap_pct, 3),
        "adapter_counters": counters,
        "status": status,
        "invalidation_reasons": invalidation_reasons,
    }


def write_capture_manifest(manifest_path: Path, sessions: list[dict], total_valid_sec: int) -> None:
    lines = [
        "# NAVIER — Manifiesto de captura prospectiva (no confirmatoria por defecto)",
        "",
        f"**Fecha de actualización:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}  ",
        "**Estado:** CAPTURA VERSIONADA; validar compatibilidad con protocolo antes de abrir resultados  ",
        "**Regla de integridad:** Datos vírgenes. No consultar residuos ni evaluar modelos predictivos hasta Fase 5.  ",
        "",
        "---",
        "",
        "## 1. Resumen Global de Validación",
        "",
        f"- **Total de sesiones registradas:** {len(sessions)}",
        f"- **Sesiones válidas aprobadas:** {sum(1 for s in sessions if s['status'] == 'VALID')}",
        f"- **Total segundos 1s válidos:** {total_valid_sec}",
        f"- **Criterio mínimo de protocolo:** $\\ge 6\\,500$ observaciones limpias",
        f"- **Estado de cumplimiento:** {'CUMPLIDO' if total_valid_sec >= 6500 else 'EN PROGRESO'}",
        "",
        "---",
        "",
        "## 2. Detalle de Sesiones Capturadas",
        "",
        "| Sesión | Símbolo | Inicio (UTC) | Fin (UTC) | Filas 1s | Gaps (%) | CRC32 Fail | Estado | Hash SHA-256 (1s) |",
        "|---|---|---|---|---|---|---|---|---|",
    ]

    for s in sessions:
        h_short = s["resampled_sha256"][:16] + "..." if s.get("resampled_sha256") else "N/A"
        lines.append(
            f"| {s['session_index']} | {s['symbol']} | {s['started_at_utc']} | {s['ended_at_utc']} | "
            f"{s['total_seconds_1s']} | {s['gap_pct']}% | {s['adapter_counters'].get('checksum_failures', 0)} | "
            f"**{s['status']}** | `{h_short}` |"
        )

    lines.extend([
        "",
        "---",
        "",
        "## 3. Hashes Criptográficos SHA-256 Completos de los Archivos 1s",
        "",
        "| Archivo | Hash SHA-256 Completo |",
        "|---|---|",
    ])

    for s in sessions:
        if s.get("resampled_file") and s.get("resampled_sha256"):
            lines.append(f"| `{s['resampled_file']}` | `{s['resampled_sha256']}` |")

    lines.append("")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sessions", type=int, default=9, help="Número de sesiones a capturar (mínimo 9)")
    parser.add_argument("--duration-sec", type=int, default=2400, help="Duración por sesión en segundos (~40 min = 2400)")
    parser.add_argument("--symbol", default="BTC/USDT", help="Símbolo Kraken Spot (BTC/USDT difiere del BTC/USD del protocolo V3 congelado)")
    parser.add_argument("--depth", type=int, default=10, help="Profundidad de niveles L2")
    parser.add_argument("--output-dir", default="data/v3_prospective", help="Raíz de salida versionada; crea un subdirectorio único por ejecución")
    args = parser.parse_args()

    if args.sessions < 1 or args.duration_sec < 1:
        parser.error("--sessions y --duration-sec deben ser positivos")
    base_out_dir = Path(args.output_dir).expanduser().resolve()
    run_id = datetime.now(timezone.utc).strftime("run_%Y%m%dT%H%M%S_%fZ")
    out_dir = base_out_dir / run_id
    out_dir.mkdir(parents=True, exist_ok=False)

    manifest_md_path = out_dir / "capture_manifest.md"

    log("=" * 70)
    log("NAVIER — INICIO DE CAPTURA PROSPECTIVA (NO CONFIRMATORIA POR DEFECTO)")
    log(f"Objetivo: {args.sessions} sesiones de {args.duration_sec}s (~{args.duration_sec/60:.1f} min)")
    log(f"Directorio: {out_dir}")
    log(f"Símbolo: {args.symbol}; BTC/USDT no coincide con el instrumento BTC/USD del protocolo V3 congelado.")
    log("=" * 70)

    session_reports = []
    total_valid_sec = 0

    for idx in range(1, args.sessions + 1):
        log(f"\n>>> INICIANDO SESIÓN {idx}/{args.sessions} <<<")
        rep = capture_session(idx, args.symbol, args.depth, args.duration_sec, out_dir)
        session_reports.append(rep)
        if rep["status"] == "VALID":
            total_valid_sec += rep["total_seconds_1s"]
        log(f"Resultado sesión {idx}: {rep['status']} | Segundos 1s: {rep['total_seconds_1s']} | Gaps: {rep['gap_pct']}%")

        write_capture_manifest(manifest_md_path, session_reports, total_valid_sec)

    log("\n" + "=" * 70)
    log(f"FASE 3 COMPLETADA. Total segundos limpios acumulados: {total_valid_sec}")
    log(f"Manifiesto guardado en: {manifest_md_path}")
    log("=" * 70)


if __name__ == "__main__":
    main()
