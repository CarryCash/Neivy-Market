"""NAVIER V3 — Runner histórico (la entrada pública usa el runner purgado).

Ejecuta la función congelada `evaluate_dataset_v3` sobre `data/research_dataset_v3.parquet`
conforme a los requisitos estrictos de auditoría de Fase 5:
- Verificación criptográfica previa de entradas y código congelado.
- Validación de esquema, tipos y orden temporal.
- Registro exhaustivo de metadatos del entorno y configuración.
- Ejecución única y no destructiva en nuevo directorio `results/phase5_v3/`.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import platform
import sys
import time
import traceback

import numpy as np
import pandas as pd
import scipy

# Configurar sys.path para resolución de módulos del proyecto
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.evaluate_models_oos_v3 import evaluate_dataset_v3, MODEL_SPECS_V3, FUTILITY_DELTA_MIN
from navier_lab.features import TARGET


def compute_sha256(path: Path) -> str:
    """Calcula SHA-256 de un archivo en bloques de 64 KB."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest().lower()


def verify_frozen_manifest(manifest_path: Path, project_root: Path) -> list[dict]:
    """Verifica cada par ruta-hash en docs/v3_freeze_manifest.md."""
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifiesto congelado no encontrado: {manifest_path}")

    records = []
    lines = manifest_path.read_text(encoding="utf-8").splitlines()
    for line in lines:
        if "|" in line:
            parts = [p.strip() for p in line.split("|")]
            # markdown table: | col1 | col2 | col3 | -> parts has at least 4 items: ['', 'Componente', 'Archivo', 'Hash', '']
            if len(parts) >= 5 and parts[2] and parts[3]:
                fpath_cand = parts[2].strip("`").replace("\\", "/")
                hash_cand = parts[3].strip("`").lower()
                if len(hash_cand) == 64 and all(c in "0123456789abcdef" for c in hash_cand):
                    full_p = project_root / fpath_cand
                    if full_p.exists():
                        actual_h = compute_sha256(full_p)
                        match = (actual_h == hash_cand)
                        records.append({
                            "path": fpath_cand,
                            "expected_sha256": hash_cand,
                            "actual_sha256": actual_h,
                            "match": match,
                        })
                        if not match:
                            raise ValueError(f"Fallo de integridad en archivo congelado: {fpath_cand}")
    if len(records) < 7:
        raise ValueError(f"Se esperaban al menos 7 archivos congelados, encontrados: {len(records)}")
    return records


def verify_dataset_integrity(parquet_path: Path, manifest_path: Path) -> dict:
    """Verifica el hash del dataset frente a su manifiesto de construcción."""
    if not parquet_path.exists():
        raise FileNotFoundError(f"Dataset no encontrado: {parquet_path}")
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifiesto del dataset no encontrado: {manifest_path}")

    with open(manifest_path, "r", encoding="utf-8") as f:
        m = json.load(f)

    expected_h = m.get("output_sha256", "").lower()
    actual_h = compute_sha256(parquet_path)

    if actual_h != expected_h:
        raise ValueError(
            f"Fallo de integridad en dataset Parquet!\n"
            f"  Esperado (manifiesto): {expected_h}\n"
            f"  Calculado:             {actual_h}"
        )

    return {
        "parquet_path": str(parquet_path.relative_to(parquet_path.parents[1])),
        "expected_sha256": expected_h,
        "actual_sha256": actual_h,
        "match": True,
        "manifest_total_rows": m.get("total_valid_rows"),
        "manifest_total_cols": m.get("total_columns"),
    }


def validate_input_dataframe(df: pd.DataFrame) -> dict:
    """Valida esquema, orden temporal y condiciones requeridas por evaluate_dataset_v3."""
    # 1. Columnas obligatorias
    required_cols = list(MODEL_SPECS_V3["Model_E"]) + [TARGET, "timestamp", "session_id"]
    # Para interacciones de B++ se necesitan:
    extra_needed = ["ofi_5", "imb_full", "depth_log"]
    all_needed = set(required_cols + extra_needed)
    missing = [c for c in all_needed if c not in df.columns and not c.startswith("_")]
    if missing:
        raise ValueError(f"Columnas requeridas ausentes en el DataFrame: {missing}")

    # 2. Tipos de datos
    if not pd.api.types.is_datetime64_any_dtype(df["timestamp"]):
        raise TypeError(f"Columna 'timestamp' debe ser datetime64, se obtuvo: {df['timestamp'].dtype}")

    # 3. Orden temporal por sesión
    sessions = df["session_id"].unique()
    for s in sessions:
        sub = df[df["session_id"] == s]
        if not sub["timestamp"].is_monotonic_increasing:
            raise ValueError(f"Timestamps no monótonos en sesión {s}")
        # Duplicados temporales en misma sesión
        dup_ts = sub["timestamp"].duplicated().sum()
        if dup_ts > 0:
            raise ValueError(f"Existen {dup_ts} timestamps duplicados dentro de sesión {s}")

    return {
        "num_rows": len(df),
        "num_cols": len(df.columns),
        "sessions": list(sessions),
        "num_sessions": len(sessions),
        "timestamp_start": str(df["timestamp"].min()),
        "timestamp_end": str(df["timestamp"].max()),
        "validation_passed": True,
    }


def _run_phase5_evaluation_legacy():
    start_time_utc = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    start_time_monotonic = time.monotonic()
    print("=" * 80)
    print("NAVIER V3 — RUNNER CONTROLADO DE EVALUACIÓN FUERA DE MUESTRA (FASE 5)")
    print(f"Inicio: {start_time_utc}")
    print("=" * 80)

    # Rutas canónicas
    manifest_frozen = PROJECT_ROOT / "docs" / "v3_freeze_manifest.md"
    dataset_parquet = PROJECT_ROOT / "data" / "research_dataset_v3.parquet"
    dataset_manifest = PROJECT_ROOT / "data" / "research_dataset_v3.manifest.json"
    results_dir = PROJECT_ROOT / "results" / "phase5_v3"
    results_dir.mkdir(parents=True, exist_ok=True)

    metadata = {
        "execution_start_utc": start_time_utc,
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python_version": sys.version,
            "python_executable": sys.executable,
        },
        "dependency_versions": {
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "scipy": scipy.__version__,
        },
        "command_line": sys.argv,
        "parameters": {
            "holdout_ratio": 0.20,
            "k_folds": 5,
            "purge": 10,
            "embargo": 10,
            "seed": 42,
            "futility_delta_min": FUTILITY_DELTA_MIN,
        },
    }

    try:
        # Paso 1: Verificación de archivos congelados
        print("\n[1/5] Verificando integridad criptográfica de código congelado...")
        frozen_records = verify_frozen_manifest(manifest_frozen, PROJECT_ROOT)
        metadata["frozen_files_verification"] = frozen_records
        for r in frozen_records:
            print(f"  [OK] {r['path']} -> {r['actual_sha256'][:16]}...")

        # Paso 2: Verificación de integridad del dataset
        print("\n[2/5] Verificando integridad criptográfica de research_dataset_v3.parquet...")
        ds_verification = verify_dataset_integrity(dataset_parquet, dataset_manifest)
        metadata["dataset_verification"] = ds_verification
        print(f"  [OK] SHA-256 Coincide: {ds_verification['actual_sha256']}")
        print(f"  [OK] Filas esperadas: {ds_verification['manifest_total_rows']}")

        # Paso 3: Carga y validación del DataFrame
        print("\n[3/5] Cargando dataset y validando esquema...")
        df = pd.read_parquet(dataset_parquet)
        df_val = validate_input_dataframe(df)
        metadata["dataframe_validation"] = df_val
        print(f"  [OK] Filas cargadas: {df_val['num_rows']} | Columnas: {df_val['num_cols']}")
        print(f"  [OK] Sesiones válidas: {df_val['num_sessions']} ({df_val['sessions']})")
        print(f"  [OK] Rango temporal: {df_val['timestamp_start']} -> {df_val['timestamp_end']}")

        # Paso 4: Ejecución formal única de la función congelada evaluate_dataset_v3
        print("\n[4/5] Ejecutando evaluate_dataset_v3 (Walk-Forward k=5, Purga/Embargo=10s, Holdout=20%)...")
        eval_start = time.monotonic()
        results = evaluate_dataset_v3(
            df_raw_features=df,
            holdout_ratio=0.20,
            k_folds=5,
            purge=10,
            embargo=10,
            seed=42,
        )
        eval_elapsed_sec = round(time.monotonic() - eval_start, 3)
        print(f"  [OK] Evaluación completada en {eval_elapsed_sec} segundos.")

        # Paso 5: Guardado estricto en directorio nuevo results/phase5_v3/
        print("\n[5/5] Guardando resultados en results/phase5_v3/...")
        total_elapsed_sec = round(time.monotonic() - start_time_monotonic, 3)
        metadata["execution_end_utc"] = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
        metadata["evaluation_duration_seconds"] = eval_elapsed_sec
        metadata["total_duration_seconds"] = total_elapsed_sec
        metadata["status"] = "SUCCESS"

        out_results_path = results_dir / "oos_evaluation_results.json"
        out_meta_path = results_dir / "execution_metadata.json"

        out_results_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
        out_meta_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")

        print(f"  [OK] Resultados guardados en: {out_results_path}")
        print(f"  [OK] Metadatos guardados en: {out_meta_path}")

        # Resumen del veredicto
        verdict = results.get("verdict")
        crit = results.get("criteria_breakdown", {})
        c1 = results.get("walk_forward_comparisons", {}).get("Model_E_vs_Model_B_tripleplus", {})
        ho = results.get("holdout_comparisons", {}).get("Model_E_vs_Model_B_tripleplus", {})

        print("\n" + "=" * 80)
        print("VEREDICTO FORMAL DE EVALUACIÓN FUERA DE MUESTRA V3 (FASE 5):")
        print(f"  Veredicto Determinista: {verdict}")
        print("-" * 80)
        print("  Contraste Primario C1 (Model_E vs Model_B_tripleplus):")
        print(f"    Walk-Forward Delta R2 OOS:   {c1.get('delta_r2_oos'):+.6f} ({c1.get('delta_r2_oos')*100:+.4f}%)")
        print(f"    95% CI Bootstrap Estacionario: [{c1.get('ci_95', [0, 0])[0]:+.6f}, {c1.get('ci_95', [0, 0])[1]:+.6f}]")
        print(f"    DM t-stat (L=20):           {c1.get('dm_t_stat'):+.4f} | p-valor: {c1.get('dm_p_value'):.4e}")
        print(f"    DM p-valor Ajustado (FDR):  {c1.get('dm_p_fdr_adjusted'):.4e}")
        print(f"    Consistencia Folds:         {c1.get('folds_positive_count')}/{c1.get('folds_total')} ({c1.get('folds_positive_ratio')*100:.0f}%)")
        print(f"    Holdout Delta R2 OOS:       {ho.get('delta_r2_oos_holdout'):+.6f} ({ho.get('delta_r2_oos_holdout')*100:+.4f}%)")
        print(f"    Holdout DM t-stat / p-val:  {ho.get('dm_t_stat'):+.4f} | p={ho.get('dm_p_value'):.4e}")
        print("=" * 80)

    except Exception as exc:
        print(f"\n[ERROR CRÍTICO] La evaluación falló: {exc}")
        metadata["status"] = "FAILED"
        metadata["error_message"] = str(exc)
        metadata["traceback"] = traceback.format_exc()
        out_meta_path = results_dir / "execution_metadata_error.json"
        out_meta_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    from scripts.run_phase5_evaluation_purged import main
    main()
