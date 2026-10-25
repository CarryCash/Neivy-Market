"""Orquestador automatizado para captura, auditoría y evaluación de sesiones restantes (Fases 3, 4 y 5).

Ejecuta secuencialmente:
1. Captura en vivo de Kraken L2 (BTC/USD, depth 10, 900 s por sesión) con checksums CRC32.
2. Control de calidad y auditoría de integridad por sesión.
3. Resampleo causal a 1.0s y consolidación del dataset de investigación.
4. Evaluación predictiva fuera de muestra (Walk-Forward OOS + hold-out intacto).
"""
from __future__ import annotations

import argparse
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


def run_command(cmd: list[str], description: str) -> bool:
    log(f"Iniciando: {description}...")
    log(f"Comando: {' '.join(cmd)}")
    start = time.monotonic()
    proc = subprocess.run(cmd, cwd=str(PROJECT_ROOT), capture_output=True, text=True)
    elapsed = time.monotonic() - start
    
    if proc.returncode != 0:
        log(f"ERROR en {description} (código {proc.returncode}, {elapsed:.1f}s):")
        if proc.stdout:
            print("--- STDOUT ---", flush=True)
            print(proc.stdout[-2000:], flush=True)
        if proc.stderr:
            print("--- STDERR ---", flush=True)
            print(proc.stderr[-2000:], flush=True)
        return False

    log(f"COMPLETADO con éxito: {description} ({elapsed:.1f}s)")
    if proc.stdout:
        # Imprimir las últimas líneas relevantes
        lines = [line.strip() for line in proc.stdout.strip().splitlines() if line.strip()]
        for l in lines[-6:]:
            print(f"   | {l}", flush=True)
    return True


def run_pipeline(start_session: int, end_session: int, duration_sec: int, symbol: str, depth: int) -> None:
    log("=" * 70)
    log(f"INICIANDO PIPELINE DE SESIONES {start_session} A {end_session}")
    log(f"Símbolo: {symbol} | Profundidad: {depth} | Duración/sesión: {duration_sec}s (~{duration_sec/60:.1f} min)")
    log("=" * 70)

    for s_idx in range(start_session, end_session + 1):
        session_name = f"session_{s_idx}_btc_usd_l2"
        raw_output = PROJECT_ROOT / "data" / "kraken" / "sessions" / f"{session_name}.parquet"
        eval_output = PROJECT_ROOT / "results" / f"oos_model_evaluation_sessions1_{s_idx}.json"

        log("-" * 60)
        log(f"PASO 1/4: Capturando {session_name} ({duration_sec} segundos)...")
        capture_cmd = [
            PYTHON_EXE,
            str(PROJECT_ROOT / "scripts" / "capture_kraken_l2.py"),
            "--symbol", symbol,
            "--depth", str(depth),
            "--seconds", str(duration_sec),
            "--output", str(raw_output),
            "--overwrite"
        ]
        ok = run_command(capture_cmd, f"Captura {session_name}")
        if not ok:
            log(f"Abortando pipeline en sesión {s_idx} debido a fallo en captura.")
            sys.exit(1)

        log(f"PASO 2/4: Reconstrucción y resampleo causal del dataset de investigación...")
        build_cmd = [
            PYTHON_EXE,
            str(PROJECT_ROOT / "scripts" / "build_research_dataset.py"),
            "--sessions-dir", str(PROJECT_ROOT / "data" / "kraken" / "sessions"),
            "--output", str(PROJECT_ROOT / "data" / "research_dataset_v2.parquet")
        ]
        ok = run_command(build_cmd, f"Construcción dataset multisesión (hasta sesión {s_idx})")
        if not ok:
            log(f"Abortando pipeline en sesión {s_idx} debido a fallo en resampleo/features.")
            sys.exit(1)

        log(f"PASO 3/4: Auditoría de calidad multisesión...")
        audit_cmd = [
            PYTHON_EXE,
            str(PROJECT_ROOT / "scripts" / "audit_sessions_quality.py"),
            "--sessions-dir", str(PROJECT_ROOT / "data" / "kraken" / "sessions"),
            "--output-json", str(PROJECT_ROOT / "results" / "session_quality_audit.json")
        ]
        ok = run_command(audit_cmd, f"Auditoría de calidad (hasta sesión {s_idx})")
        if not ok:
            log(f"Advertencia: Falló auditoría de calidad para sesión {s_idx}.")

        log(f"PASO 4/4: Evaluación predictiva OOS acumulada (Sesiones 1 a {s_idx})...")
        eval_cmd = [
            PYTHON_EXE,
            str(PROJECT_ROOT / "scripts" / "evaluate_models_oos.py"),
            "--input", str(PROJECT_ROOT / "data" / "research_dataset_v2.parquet"),
            "--output-json", str(eval_output)
        ]
        ok = run_command(eval_cmd, f"Evaluación OOS (sesiones 1 a {s_idx})")
        if not ok:
            log(f"Advertencia: Falló evaluación OOS para sesión {s_idx}.")

        log(f"Sesión {s_idx} procesada y consolidada exitosamente.")
        time.sleep(2)

    log("=" * 70)
    log(f"PIPELINE COMPLETADO EXITOSAMENTE (SESIONES {start_session} A {end_session})")
    log("=" * 70)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-session", type=int, default=10, help="Índice de sesión inicial")
    parser.add_argument("--end-session", type=int, default=14, help="Índice de sesión final")
    parser.add_argument("--seconds", type=int, default=900, help="Segundos por sesión (default 900s = 15m)")
    parser.add_argument("--symbol", default="BTC/USD", help="Par de trading Kraken")
    parser.add_argument("--depth", type=int, default=10, help="Profundidad de niveles L2")
    args = parser.parse_args()

    run_pipeline(args.start_session, args.end_session, args.seconds, args.symbol, args.depth)


if __name__ == "__main__":
    main()
