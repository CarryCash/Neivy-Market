"""Non-overwriting runner for the post-hoc timestamp-purged V3 diagnostic."""
from __future__ import annotations

import argparse
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

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.evaluate_models_oos_v3 import evaluate_dataset_v3, MODEL_SPECS_V3, FUTILITY_DELTA_MIN
from scripts.evaluate_models_oos_v3_temporal import validate_temporal_dataframe
from navier_lab.features import TARGET


def compute_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().lower()


def verify_correction_manifest(manifest_path: Path) -> list[dict]:
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifiesto de corrección ausente: {manifest_path}")
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    records = []
    for item in data.get("files", []):
        relative = item["path"].replace("\\", "/")
        expected = item["sha256"].lower()
        source = (PROJECT_ROOT / relative).resolve()
        if PROJECT_ROOT.resolve() not in source.parents:
            raise ValueError(f"Ruta fuera del proyecto en manifiesto: {relative}")
        if not source.exists():
            raise FileNotFoundError(f"Archivo congelado ausente: {relative}")
        actual = compute_sha256(source)
        if actual != expected:
            raise ValueError(f"Hash no coincide para {relative}: {actual} != {expected}")
        records.append({"path": relative, "expected_sha256": expected, "actual_sha256": actual, "match": True})
    if not records:
        raise ValueError("El manifiesto de corrección no contiene archivos")
    return records


def verify_dataset(dataset_path: Path, manifest_path: Path) -> tuple[dict, dict]:
    if not dataset_path.exists() or not manifest_path.exists():
        raise FileNotFoundError("Falta el dataset temporal corregido o su manifiesto")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    actual = compute_sha256(dataset_path)
    expected = manifest.get("output_sha256", "").lower()
    if actual != expected:
        raise ValueError(f"Hash dataset incorrecto: {actual} != {expected}")
    horizon = int(manifest.get("parameters", {}).get("horizon_seconds", 0))
    if horizon <= 0:
        raise ValueError("El manifiesto no declara un horizonte positivo")
    return manifest, {
        "path": str(dataset_path.relative_to(PROJECT_ROOT)),
        "sha256": actual,
        "manifest_sha256": compute_sha256(manifest_path),
        "rows": manifest.get("total_valid_rows"),
        "columns": manifest.get("total_columns"),
        "horizon_seconds": horizon,
    }


def validate_dataframe(df: pd.DataFrame, horizon_seconds: int) -> dict:
    required = set(MODEL_SPECS_V3["Model_E"] + [TARGET, "ofi_5", "imb_full", "depth_log"])
    missing = sorted(col for col in required - set(df.columns) if not col.startswith("_"))
    if missing:
        raise ValueError(f"Columnas de features requeridas ausentes: {missing}")
    temporal = validate_temporal_dataframe(df, expected_horizon_seconds=horizon_seconds)
    return {
        "num_rows": len(temporal),
        "num_cols": len(temporal.columns),
        "sessions": temporal["session_id"].astype(str).drop_duplicates().tolist(),
        "num_sessions": int(temporal["session_id"].nunique()),
        "timestamp_start": temporal["feature_time"].min().isoformat(),
        "timestamp_end": temporal["feature_time"].max().isoformat(),
        "label_end_max": temporal["label_end_time"].max().isoformat(),
        "temporal_schema_validated": True,
    }


def run_phase5_evaluation(
    dataset_path: Path,
    dataset_manifest_path: Path,
    results_dir: Path,
    n_boot: int = 1000,
) -> dict:
    results_dir = results_dir.expanduser().resolve()
    dataset_path = dataset_path.expanduser().resolve()
    dataset_manifest_path = dataset_manifest_path.expanduser().resolve()
    if results_dir.exists() and any(results_dir.iterdir()):
        raise FileExistsError(f"Directorio de resultados no vacío; no se sobrescribe: {results_dir}")

    # Fail integrity preflight before creating an output directory.
    correction_manifest = PROJECT_ROOT / "docs" / "v3_temporal_correction_manifest.json"
    correction_records = verify_correction_manifest(correction_manifest)
    dataset_manifest, dataset_integrity = verify_dataset(dataset_path, dataset_manifest_path)
    df = pd.read_parquet(dataset_path)
    dataframe_audit = validate_dataframe(df, dataset_integrity["horizon_seconds"])
    results_dir.mkdir(parents=True, exist_ok=True)

    started = time.monotonic()
    metadata = {
        "status": "RUNNING",
        "evidence_status": "POST_HOC_DIAGNOSTIC_NOT_CONFIRMATORY",
        "execution_start_utc": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "platform": {
            "system": platform.system(), "release": platform.release(),
            "machine": platform.machine(), "python_version": sys.version,
            "python_executable": sys.executable,
        },
        "dependency_versions": {
            "numpy": np.__version__, "pandas": pd.__version__, "scipy": scipy.__version__,
        },
        "command_line": sys.argv,
        "parameters": {
            "holdout_ratio": 0.20, "k_folds": 5,
            "purge_rule": "label_end_time < nominal test_start_time",
            "embargo_seconds": 10, "seed": 42, "n_boot": n_boot,
            "bootstrap_block_seconds": [10, 15, 30],
            "fdr_family": "C1-C4; primary block length 15s",
            "futility_delta_min": FUTILITY_DELTA_MIN,
        },
        "correction_code_verification": correction_records,
        "dataset_verification": dataset_integrity,
        "dataset_manifest_parameters": dataset_manifest.get("parameters", {}),
        "dataframe_validation": dataframe_audit,
    }
    result_path = results_dir / "oos_evaluation_results.json"
    metadata_path = results_dir / "execution_metadata.json"
    error_path = results_dir / "execution_metadata_error.json"
    try:
        evaluation_started = time.monotonic()
        results = evaluate_dataset_v3(
            df_raw_features=df,
            holdout_ratio=0.20,
            k_folds=5,
            embargo_seconds=10,
            seed=42,
            expected_horizon_seconds=dataset_integrity["horizon_seconds"],
            n_boot=n_boot,
        )
        metadata["evaluation_duration_seconds"] = round(time.monotonic() - evaluation_started, 3)
        metadata["status"] = "SUCCESS"
        metadata["execution_end_utc"] = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
        metadata["total_duration_seconds"] = round(time.monotonic() - started, 3)
        c1 = results["walk_forward_comparisons"]["Model_E_vs_Model_B_tripleplus"]
        print(f"Post-hoc evaluation saved to {result_path}")
        print(f"Evidence status: {results['evidence_status']}")
        print(
            "C1 WF delta_R2={:+.6%}, bootstrap-15s p={:.4g}, FDR={:.4g}; N={}".format(
                c1["delta_r2_oos"], c1["block_bootstrap_p_value"],
                c1["block_bootstrap_p_fdr_adjusted"], c1["n_eval_obs"],
            )
        )
        print("No train/test label overlap:", results["temporal_audit"]["all_train_labels_end_before_test"])
        result_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
        metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
        return results
    except Exception as exc:
        metadata["status"] = "FAILED"
        metadata["error_message"] = str(exc)
        metadata["traceback"] = traceback.format_exc()
        metadata["execution_end_utc"] = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
        metadata["total_duration_seconds"] = round(time.monotonic() - started, 3)
        error_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default="data/research_dataset_v3_temporal_purged.parquet")
    parser.add_argument("--dataset-manifest", default="data/research_dataset_v3_temporal_purged.manifest.json")
    parser.add_argument("--results-dir", default="results/phase5_v3_purged_run4")
    parser.add_argument("--n-boot", type=int, default=1000)
    args = parser.parse_args()
    run_phase5_evaluation(
        PROJECT_ROOT / args.dataset,
        PROJECT_ROOT / args.dataset_manifest,
        PROJECT_ROOT / args.results_dir,
        n_boot=args.n_boot,
    )


if __name__ == "__main__":
    main()
