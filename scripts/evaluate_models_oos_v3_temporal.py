"""Post-hoc V3 temporal correction.

The original V3 result has already been inspected. Results produced here are
diagnostic and cannot restore a confirmatory holdout. Label intervals are
explicit, purging is timestamp-based, and inference resamples paired losses in
time blocks without joining sessions, folds, or long gaps.
"""
from __future__ import annotations

import time

import numpy as np
import pandas as pd

from navier_lab.analysis import bh_adjust
from navier_lab.features import NAVIER_V3_REPLENISH, TARGET
from scripts.evaluate_models_oos_v3 import (
    CONFIRMATORY_PAIRS,
    FUTILITY_DELTA_MIN,
    MODEL_SPECS_V3,
    classify_v3_verdict,
    fit_and_predict_wf,
    paired_oos_r2,
    prepare_feature_dataframe,
)

BOOTSTRAP_BLOCK_SECONDS = (10, 15, 30)
DEFAULT_BOOTSTRAP_REPLICATES = 1000


def validate_temporal_dataframe(
    df: pd.DataFrame, expected_horizon_seconds: int | None = None
) -> pd.DataFrame:
    """Validate exact target metadata, then return a stable chronological copy.

    `feature_time` is the one-second resampled market timestamp available to the
    historical model. It is not exchange-to-client receive time; that latency is
    not present in the frozen research dataset.
    """
    required = [
        "timestamp", "feature_time", "label_start_time", "label_end_time",
        "label_end_session_id", "label_horizon_seconds", "session_id", TARGET,
    ]
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise ValueError(f"Faltan metadatos temporales obligatorios: {missing}")
    if df.index.has_duplicates:
        raise ValueError("El índice del DataFrame contiene duplicados")
    if df.empty:
        raise ValueError("El DataFrame temporal está vacío")

    work = df.copy()
    for col in ("timestamp", "feature_time", "label_start_time", "label_end_time"):
        if not pd.api.types.is_datetime64_any_dtype(work[col].dtype):
            raise TypeError(f"{col} debe tener dtype datetime64 con zona horaria")
        if getattr(work[col].dt, "tz", None) is None:
            raise TypeError(f"{col} debe incluir zona horaria")
        work[col] = work[col].dt.tz_convert("UTC")
        if work[col].isna().any():
            raise ValueError(f"{col} contiene timestamps ausentes")

    if work["session_id"].isna().any() or work["label_end_session_id"].isna().any():
        raise ValueError("session_id y label_end_session_id no pueden estar ausentes")
    if not work["timestamp"].equals(work["feature_time"]):
        raise ValueError("timestamp y feature_time deben identificar el mismo estado de mercado")
    if not work["label_start_time"].equals(work["feature_time"]):
        raise ValueError("label_start_time debe coincidir con feature_time para el retorno t→t+H")
    if not work["session_id"].astype(str).equals(work["label_end_session_id"].astype(str)):
        raise ValueError("Una o más etiquetas terminan fuera de su sesión de origen")

    horizons = pd.to_numeric(work["label_horizon_seconds"], errors="coerce")
    if horizons.isna().any() or (horizons <= 0).any():
        raise ValueError("label_horizon_seconds debe ser positivo y estar presente")
    if horizons.nunique() != 1:
        raise ValueError("El dataset mezcla horizontes de etiqueta")
    horizon_seconds = int(horizons.iloc[0])
    if float(horizons.iloc[0]) != horizon_seconds:
        raise ValueError("El horizonte debe ser un número entero de segundos")
    if expected_horizon_seconds is not None and horizon_seconds != expected_horizon_seconds:
        raise ValueError(
            f"El dataset declara H={horizon_seconds}s, se esperaba H={expected_horizon_seconds}s"
        )
    actual_seconds = (work["label_end_time"] - work["label_start_time"]).dt.total_seconds()
    if not np.allclose(actual_seconds.to_numpy(float), horizon_seconds, rtol=0, atol=1e-9):
        raise ValueError("label_end_time no coincide con el horizonte efectivo de cada etiqueta")

    if work["feature_time"].duplicated().any():
        raise ValueError("Hay feature_time duplicados; la partición cronológica es ambigua")
    work = work.sort_values(["feature_time", "session_id"], kind="mergesort").reset_index(drop=True)
    return work


def _eligible_training_indices(
    df: pd.DataFrame, candidate_indices: np.ndarray, test_start_time: pd.Timestamp
) -> tuple[np.ndarray, int]:
    """Admit only rows whose exact label endpoint is strictly before test."""
    if len(candidate_indices) == 0:
        return np.array([], dtype=int), 0
    end_ns = df["label_end_time"].array.asi8[candidate_indices]
    start_ns = pd.Timestamp(test_start_time).tz_convert("UTC").value
    eligible = candidate_indices[end_ns < start_ns]
    return eligible.astype(int), int(len(candidate_indices) - len(eligible))


def make_temporal_walk_forward_splits(
    df: pd.DataFrame,
    k_folds: int = 5,
    embargo_seconds: int = 10,
    min_train_obs: int = 50,
    min_test_obs: int = 20,
) -> list[dict]:
    """Expanding walk-forward splits; purge by label end time, embargo by time.

    Fold boundaries are selected by row quantiles for historical comparability;
    neither purge nor embargo assumes a fixed number of rows per second.
    """
    if k_folds < 2 or embargo_seconds < 0:
        raise ValueError("k_folds debe ser >=2 y embargo_seconds >=0")
    n = len(df)
    if n < k_folds * min_test_obs:
        raise ValueError(f"Muestra insuficiente para {k_folds} folds de test: n={n}")
    edges = np.linspace(0, n, k_folds + 1, dtype=int)
    if len(np.unique(edges)) != len(edges):
        raise ValueError("Folds vacíos: aumente la muestra o reduzca k_folds")

    times = df["feature_time"]
    splits: list[dict] = []
    embargo = pd.Timedelta(seconds=embargo_seconds)
    for fold_number in range(1, k_folds):
        boundary_idx = int(edges[fold_number])
        test_end_idx = int(edges[fold_number + 1])
        nominal_start = times.iloc[boundary_idx]
        candidates = np.arange(boundary_idx, test_end_idx, dtype=int)
        effective_after_embargo = nominal_start + embargo
        test_idx = candidates[
            (times.iloc[candidates] >= effective_after_embargo).to_numpy()
        ]
        train_candidates = np.arange(0, boundary_idx, dtype=int)
        train_idx, purged_count = _eligible_training_indices(df, train_candidates, nominal_start)

        if len(train_idx) < min_train_obs:
            raise ValueError(
                f"Fold {fold_number}: solo {len(train_idx)} filas train tras purga temporal; "
                f"mínimo={min_train_obs}"
            )
        if len(test_idx) < min_test_obs:
            raise ValueError(
                f"Fold {fold_number}: solo {len(test_idx)} filas test tras embargo; "
                f"mínimo={min_test_obs}"
            )
        actual_test_start = times.iloc[int(test_idx[0])]
        max_train_label_end = df["label_end_time"].iloc[train_idx].max()
        if not max_train_label_end < nominal_start or not max_train_label_end < actual_test_start:
            raise AssertionError(f"Fold {fold_number}: solapamiento temporal train/test")

        splits.append({
            "train_idx": train_idx,
            "test_idx": test_idx,
            "audit": {
                "fold": fold_number,
                "train_candidates": len(train_candidates),
                "train_obs": len(train_idx),
                "purged_train_obs": purged_count,
                "test_candidates": len(candidates),
                "embargoed_test_obs": int(len(candidates) - len(test_idx)),
                "test_obs": len(test_idx),
                "nominal_test_start_time": nominal_start.isoformat(),
                "test_start_time": actual_test_start.isoformat(),
                "test_end_time": times.iloc[int(test_idx[-1])].isoformat(),
                "max_train_label_end_time": max_train_label_end.isoformat(),
                "label_overlap": False,
            },
        })
    return splits


def make_final_holdout_split(
    df: pd.DataFrame,
    holdout_ratio: float = 0.20,
    embargo_seconds: int = 10,
    min_train_obs: int = 50,
    min_test_obs: int = 20,
) -> dict:
    """Chronological holdout with endpoint-based training purge and time embargo."""
    if not 0 < holdout_ratio < 1:
        raise ValueError("holdout_ratio debe estar entre 0 y 1")
    if embargo_seconds < 0:
        raise ValueError("embargo_seconds debe ser >=0")
    n = len(df)
    split_idx = int(n * (1.0 - holdout_ratio))
    if split_idx <= 0 or split_idx >= n:
        raise ValueError("Holdout vacío por tamaño de muestra o holdout_ratio")

    times = df["feature_time"]
    nominal_start = times.iloc[split_idx]
    train_candidates = np.arange(0, split_idx, dtype=int)
    train_idx, purged_count = _eligible_training_indices(df, train_candidates, nominal_start)
    test_candidates = np.arange(split_idx, n, dtype=int)
    effective_after_embargo = nominal_start + pd.Timedelta(seconds=embargo_seconds)
    test_idx = test_candidates[(times.iloc[test_candidates] >= effective_after_embargo).to_numpy()]

    if len(train_idx) < min_train_obs:
        raise ValueError(
            f"Holdout: solo {len(train_idx)} filas train tras purga temporal; mínimo={min_train_obs}"
        )
    if len(test_idx) < min_test_obs:
        raise ValueError(
            f"Holdout: solo {len(test_idx)} filas test tras embargo; mínimo={min_test_obs}"
        )
    max_train_label_end = df["label_end_time"].iloc[train_idx].max()
    actual_test_start = times.iloc[int(test_idx[0])]
    if not max_train_label_end < nominal_start or not max_train_label_end < actual_test_start:
        raise AssertionError("Holdout: solapamiento temporal train/test")

    return {
        "train_idx": train_idx,
        "test_idx": test_idx,
        "audit": {
            "split_index": split_idx,
            "train_candidates": len(train_candidates),
            "train_obs": len(train_idx),
            "purged_train_obs": purged_count,
            "test_candidates": len(test_candidates),
            "embargoed_test_obs": int(len(test_candidates) - len(test_idx)),
            "test_obs": len(test_idx),
            "nominal_test_start_time": nominal_start.isoformat(),
            "test_start_time": actual_test_start.isoformat(),
            "test_end_time": times.iloc[int(test_idx[-1])].isoformat(),
            "max_train_label_end_time": max_train_label_end.isoformat(),
            "label_overlap": False,
        },
    }


def _time_contiguous_segments(
    timestamps: pd.Series,
    session_ids: np.ndarray,
    fold_ids: np.ndarray,
    max_gap_seconds: int,
) -> list[np.ndarray]:
    times_ns = pd.DatetimeIndex(timestamps).asi8
    segments: list[np.ndarray] = []
    start = 0
    max_gap_ns = int(pd.Timedelta(seconds=max_gap_seconds).value)
    for i in range(1, len(times_ns)):
        boundary = (
            session_ids[i] != session_ids[i - 1]
            or fold_ids[i] != fold_ids[i - 1]
            or times_ns[i] - times_ns[i - 1] > max_gap_ns
        )
        if boundary:
            segments.append(np.arange(start, i, dtype=np.int32))
            start = i
    if len(times_ns):
        segments.append(np.arange(start, len(times_ns), dtype=np.int32))
    return segments


def time_block_bootstrap_indices(
    timestamps: pd.Series,
    session_ids: np.ndarray,
    fold_ids: np.ndarray,
    block_seconds: int,
    n_boot: int = DEFAULT_BOOTSTRAP_REPLICATES,
    seed: int = 42,
) -> np.ndarray:
    """Moving blocks in elapsed seconds; blocks never cross fold/session/long gaps."""
    if block_seconds <= 0 or n_boot <= 0:
        raise ValueError("block_seconds y n_boot deben ser positivos")
    n = len(timestamps)
    if n == 0 or len(session_ids) != n or len(fold_ids) != n:
        raise ValueError("timestamps, session_ids y fold_ids deben tener igual longitud no vacía")
    times_ns = pd.DatetimeIndex(timestamps).asi8
    if np.any(np.diff(times_ns) < 0):
        raise ValueError("timestamps del bootstrap deben estar ordenados")
    segments = _time_contiguous_segments(timestamps, session_ids, fold_ids, block_seconds)
    rng = np.random.default_rng(seed)
    draws = np.empty((n_boot, n), dtype=np.int32)
    block_ns = int(pd.Timedelta(seconds=block_seconds).value)

    for b in range(n_boot):
        output_parts = []
        for segment in segments:
            seg_times = times_ns[segment]
            sampled: list[int] = []
            target_n = len(segment)
            while len(sampled) < target_n:
                start_pos = int(rng.integers(0, target_n))
                end_time = seg_times[start_pos] + block_ns
                end_pos = int(np.searchsorted(seg_times, end_time, side="left"))
                if end_pos <= start_pos:
                    end_pos = start_pos + 1
                sampled.extend(segment[start_pos:end_pos].tolist())
            output_parts.append(np.asarray(sampled[:target_n], dtype=np.int32))
        draws[b] = np.concatenate(output_parts)
    return draws


def block_bootstrap_comparison(
    y: np.ndarray,
    pred_base: np.ndarray,
    pred_alt: np.ndarray,
    draw_indices: np.ndarray,
    ci_level: float = 0.95,
) -> dict:
    """Paired MSE contrast, percentile CI for ΔR² and centered bootstrap p-value."""
    if not (len(y) == len(pred_base) == len(pred_alt)) or len(y) == 0:
        raise ValueError("Las predicciones pareadas deben tener igual longitud no vacía")
    if not np.isfinite(y).all() or not np.isfinite(pred_base).all() or not np.isfinite(pred_alt).all():
        raise ValueError("Hay observaciones o predicciones no finitas en la comparación")
    loss_diff = (y - pred_base) ** 2 - (y - pred_alt) ** 2
    mse_base = float(np.mean((y - pred_base) ** 2))
    mse_alt = float(np.mean((y - pred_alt) ** 2))
    delta_r2 = 1.0 - mse_alt / max(1e-15, mse_base)
    observed_diff = float(loss_diff.mean())

    boot_delta = np.empty(len(draw_indices), dtype=float)
    boot_null_mean = np.empty(len(draw_indices), dtype=float)
    centered_diff = loss_diff - observed_diff
    for b, idx in enumerate(draw_indices):
        y_b = y[idx]
        base_b = pred_base[idx]
        alt_b = pred_alt[idx]
        mse_b = float(np.mean((y_b - base_b) ** 2))
        mse_a = float(np.mean((y_b - alt_b) ** 2))
        boot_delta[b] = 1.0 - mse_a / max(1e-15, mse_b)
        boot_null_mean[b] = float(centered_diff[idx].mean())

    tail = int(np.sum(np.abs(boot_null_mean) >= abs(observed_diff)))
    p_value = (tail + 1) / (len(boot_null_mean) + 1)
    alpha = (1.0 - ci_level) / 2.0
    ci = np.quantile(boot_delta, [alpha, 1.0 - alpha])
    return {
        "delta_r2_oos": float(delta_r2),
        "mse_base": mse_base,
        "mse_alt": mse_alt,
        "mean_loss_difference_base_minus_alt": observed_diff,
        "p_value": float(p_value),
        "ci_95": [float(ci[0]), float(ci[1])],
        "n_obs": len(y),
        "bootstrap_replicates": int(len(draw_indices)),
    }


def _run_block_sensitivity(
    y: np.ndarray,
    predictions: dict[str, np.ndarray],
    pairs: list[tuple[str, str]],
    times: pd.Series,
    sessions: np.ndarray,
    fold_ids: np.ndarray,
    seed: int,
    n_boot: int,
) -> dict[str, dict]:
    all_results = {f"{alt}_vs_{base}": {} for alt, base in pairs}
    for block_seconds in BOOTSTRAP_BLOCK_SECONDS:
        draws = time_block_bootstrap_indices(
            times, sessions, fold_ids, block_seconds, n_boot=n_boot, seed=seed
        )
        for alt, base in pairs:
            key = f"{alt}_vs_{base}"
            result = block_bootstrap_comparison(y, predictions[base], predictions[alt], draws)
            all_results[key][str(block_seconds)] = result
    return all_results


def _attach_metric_fields(
    target: dict, sensitivities: dict[str, dict], pairs: list[tuple[str, str]]
) -> list[float]:
    p_values = []
    for alt, base in pairs:
        key = f"{alt}_vs_{base}"
        primary = sensitivities[key]["15"]
        target[key] = {
            "alt_model": alt,
            "base_model": base,
            "delta_r2_oos": primary["delta_r2_oos"],
            "mse_base": primary["mse_base"],
            "mse_alt": primary["mse_alt"],
            "ci_95": primary["ci_95"],
            "block_bootstrap_p_value": primary["p_value"],
            "block_bootstrap_sensitivity": sensitivities[key],
            "n_eval_obs": primary["n_obs"],
            "inference_method": "paired moving-time-block bootstrap; blocks do not cross fold/session/30s gaps",
        }
        p_values.append(primary["p_value"])
    return p_values


def evaluate_dataset_v3(
    df_raw_features: pd.DataFrame,
    holdout_ratio: float = 0.20,
    k_folds: int = 5,
    embargo_seconds: int = 10,
    seed: int = 42,
    expected_horizon_seconds: int | None = None,
    n_boot: int = DEFAULT_BOOTSTRAP_REPLICATES,
    min_train_obs: int = 50,
    min_test_obs: int = 20,
) -> dict:
    """Timestamp-purged V3 evaluation; historical outputs are never written here."""
    df_full = prepare_feature_dataframe(df_raw_features)
    temporal_columns = {
        "timestamp", "feature_time", "label_start_time", "label_end_time",
        "label_end_session_id", "label_horizon_seconds", "session_id",
    }
    missing_temporal = sorted(temporal_columns - set(df_full.columns))
    if missing_temporal:
        raise ValueError(f"Faltan metadatos temporales obligatorios: {missing_temporal}")
    confirmatory_features = MODEL_SPECS_V3["Model_E"]
    clean_mask = (
        df_full[TARGET].notna()
        & df_full[confirmatory_features].notna().all(axis=1)
        & df_full["label_end_time"].notna()
    ) if "label_end_time" in df_full.columns else pd.Series(False, index=df_full.index)
    df = df_full.loc[clean_mask].copy()
    df = validate_temporal_dataframe(df, expected_horizon_seconds)
    n_total = len(df)
    if n_total < 500:
        raise ValueError(f"Muestra insuficiente tras filtro común: n={n_total}")

    split_point = int(n_total * (1.0 - holdout_ratio))
    if split_point <= 0 or split_point >= n_total:
        raise ValueError("El corte temporal produce una partición vacía")
    df_eval = df.iloc[:split_point].copy().reset_index(drop=True)
    wf_splits = make_temporal_walk_forward_splits(
        df_eval,
        k_folds=k_folds,
        embargo_seconds=embargo_seconds,
        min_train_obs=min_train_obs,
        min_test_obs=min_test_obs,
    )
    n_eval = len(df_eval)
    eval_preds: dict[str, np.ndarray] = {}
    for model_name, cols in MODEL_SPECS_V3.items():
        eval_preds[model_name] = np.full(n_eval, np.nan, dtype=float)
    fold_id_by_row = np.full(n_eval, -1, dtype=int)
    test_indices = []
    split_audits = []
    for split in wf_splits:
        train_idx, test_idx = split["train_idx"], split["test_idx"]
        for model_name, cols in MODEL_SPECS_V3.items():
            X = df_eval[cols].to_numpy(float)
            pred = fit_and_predict_wf(X, df_eval[TARGET].to_numpy(float), [(train_idx, test_idx)])
            eval_preds[model_name][test_idx] = pred[test_idx]
        fold_id_by_row[test_idx] = split["audit"]["fold"]
        test_indices.append(test_idx)
        split_audits.append(split["audit"])

    test_indices_all = np.concatenate(test_indices)
    if len(np.unique(test_indices_all)) != len(test_indices_all):
        raise AssertionError("Una observación aparece en más de un fold test")
    test_indices_all.sort()
    test_mask = np.zeros(n_eval, dtype=bool)
    test_mask[test_indices_all] = True
    y_eval_all = df_eval[TARGET].to_numpy(float)
    y_eval = y_eval_all[test_mask]
    wf_predictions = {name: values[test_mask] for name, values in eval_preds.items()}
    wf_times = df_eval["feature_time"].iloc[test_indices_all].reset_index(drop=True)
    wf_sessions = df_eval["session_id"].iloc[test_indices_all].astype(str).to_numpy()
    wf_fold_ids = fold_id_by_row[test_indices_all]

    wf_sensitivities = _run_block_sensitivity(
        y_eval, wf_predictions, CONFIRMATORY_PAIRS, wf_times, wf_sessions,
        wf_fold_ids, seed, n_boot,
    )
    wf_comparisons: dict[str, dict] = {}
    wf_p_values = _attach_metric_fields(wf_comparisons, wf_sensitivities, CONFIRMATORY_PAIRS)
    adjusted_p = bh_adjust(np.asarray(wf_p_values, dtype=float))
    for i, (alt, base) in enumerate(CONFIRMATORY_PAIRS):
        key = f"{alt}_vs_{base}"
        wf_comparisons[key]["block_bootstrap_p_fdr_adjusted"] = float(adjusted_p[i])
        fold_deltas = []
        for split in wf_splits:
            idx = split["test_idx"]
            y_fold = y_eval_all[idx]
            p_base = eval_preds[base][idx]
            p_alt = eval_preds[alt][idx]
            if not np.isfinite(p_base).all() or not np.isfinite(p_alt).all():
                raise ValueError(f"Predicciones incompletas en {key}, fold {split['audit']['fold']}")
            fold_deltas.append(paired_oos_r2(
                y_fold, p_base, p_alt, np.ones(len(idx), dtype=bool)
            )[0])
        positive = int(np.sum(np.asarray(fold_deltas) > 0))
        wf_comparisons[key].update({
            "fold_deltas": fold_deltas,
            "folds_positive_count": positive,
            "folds_total": len(wf_splits),
            "folds_positive_ratio": round(positive / len(wf_splits), 2),
        })

    # Final holdout: purge using the exact persisted endpoint, then embargo in seconds.
    holdout_split = make_final_holdout_split(
        df, holdout_ratio=holdout_ratio, embargo_seconds=embargo_seconds,
        min_train_obs=min_train_obs, min_test_obs=min_test_obs,
    )
    train_ho = df.iloc[holdout_split["train_idx"]].copy()
    test_ho = df.iloc[holdout_split["test_idx"]].copy()
    y_ho = test_ho[TARGET].to_numpy(float)
    holdout_preds: dict[str, np.ndarray] = {}
    for model_name, cols in MODEL_SPECS_V3.items():
        X_train = train_ho[cols].to_numpy(float)
        y_train = train_ho[TARGET].to_numpy(float)
        mu = X_train.mean(axis=0)
        sd = X_train.std(axis=0) + 1e-12
        X_train_std = np.clip((X_train - mu) / sd, -5.0, 5.0)
        A = np.c_[np.ones(len(X_train_std)), X_train_std]
        ridge = 1e-6 * len(X_train_std) * np.eye(A.shape[1])
        ridge[0, 0] = 0.0
        beta = np.linalg.solve(A.T @ A + ridge, A.T @ y_train)
        X_test_std = np.clip((test_ho[cols].to_numpy(float) - mu) / sd, -5.0, 5.0)
        holdout_preds[model_name] = beta[0] + X_test_std @ beta[1:]

    holdout_fold_ids = np.zeros(len(test_ho), dtype=int)
    ho_sensitivities = _run_block_sensitivity(
        y_ho, holdout_preds, CONFIRMATORY_PAIRS,
        test_ho["feature_time"].reset_index(drop=True),
        test_ho["session_id"].astype(str).to_numpy(), holdout_fold_ids,
        seed + 1, n_boot,
    )
    holdout_comparisons: dict[str, dict] = {}
    _attach_metric_fields(holdout_comparisons, ho_sensitivities, CONFIRMATORY_PAIRS)
    for key, result in holdout_comparisons.items():
        result["delta_r2_oos_holdout"] = result.pop("delta_r2_oos")
        result["n_holdout_obs"] = result.pop("n_eval_obs")

    # Exploratory H1a remains exploratory, using the same temporal split and inference.
    exploratory_cols = MODEL_SPECS_V3["Model_E"] + NAVIER_V3_REPLENISH
    clean_h1a = (
        df_full[TARGET].notna()
        & df_full[exploratory_cols].notna().all(axis=1)
        & df_full.get("label_end_time", pd.Series(index=df_full.index, dtype="datetime64[ns, UTC]")).notna()
    )
    df_h1a = validate_temporal_dataframe(
        df_full.loc[clean_h1a].copy(), expected_horizon_seconds
    )
    split_h1a = int(len(df_h1a) * (1.0 - holdout_ratio))
    df_h1a_eval = df_h1a.iloc[:split_h1a].copy().reset_index(drop=True)
    h1a_splits = make_temporal_walk_forward_splits(
        df_h1a_eval, k_folds, embargo_seconds, min_train_obs, min_test_obs
    )
    h1a_preds = {"Model_E": np.full(len(df_h1a_eval), np.nan), "Model_E_H1a": np.full(len(df_h1a_eval), np.nan)}
    h1a_fold_ids = np.full(len(df_h1a_eval), -1, dtype=int)
    for split in h1a_splits:
        tr, te = split["train_idx"], split["test_idx"]
        p_e = fit_and_predict_wf(df_h1a_eval[MODEL_SPECS_V3["Model_E"]].to_numpy(float), df_h1a_eval[TARGET].to_numpy(float), [(tr, te)])
        p_h1a = fit_and_predict_wf(df_h1a_eval[exploratory_cols].to_numpy(float), df_h1a_eval[TARGET].to_numpy(float), [(tr, te)])
        h1a_preds["Model_E"][te] = p_e[te]
        h1a_preds["Model_E_H1a"][te] = p_h1a[te]
        h1a_fold_ids[te] = split["audit"]["fold"]
    h1a_test_idx = np.flatnonzero(h1a_fold_ids >= 0)
    h1a_test_predictions = {
        "Model_E": h1a_preds["Model_E"][h1a_test_idx],
        "Model_E_H1a": h1a_preds["Model_E_H1a"][h1a_test_idx],
    }
    h1a_sensitivity = _run_block_sensitivity(
        df_h1a_eval[TARGET].to_numpy(float)[h1a_test_idx], h1a_test_predictions,
        [("Model_E_H1a", "Model_E")],
        df_h1a_eval["feature_time"].iloc[h1a_test_idx].reset_index(drop=True),
        df_h1a_eval["session_id"].iloc[h1a_test_idx].astype(str).to_numpy(),
        h1a_fold_ids[h1a_test_idx], seed + 2, n_boot,
    )["Model_E_H1a_vs_Model_E"]
    primary_h1a = h1a_sensitivity["15"]
    c5_exploratory = {
        "alt_model": "Model_E_H1a",
        "base_model": "Model_E",
        "delta_r2_oos": primary_h1a["delta_r2_oos"],
        "block_bootstrap_p_value": primary_h1a["p_value"],
        "block_bootstrap_sensitivity": h1a_sensitivity,
        "n_obs": primary_h1a["n_obs"],
        "status": "EXPLORATORIO_POST_HOC",
    }

    c1_key = "Model_E_vs_Model_B_tripleplus"
    c1_wf, c1_ho = wf_comparisons[c1_key], holdout_comparisons[c1_key]
    diagnostic_verdict = classify_v3_verdict(
        c1_wf["delta_r2_oos"], c1_wf["block_bootstrap_p_fdr_adjusted"],
        c1_wf["folds_positive_count"], c1_ho["delta_r2_oos_holdout"],
        c1_ho["block_bootstrap_sensitivity"]["15"]["p_value"],
        FUTILITY_DELTA_MIN,
    )
    return {
        "timestamp_eval": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "evidence_status": "POST_HOC_DIAGNOSTIC_NOT_CONFIRMATORY",
        "inference": {
            "method": "paired moving-time-block bootstrap",
            "primary_block_seconds": 15,
            "sensitivity_block_seconds": list(BOOTSTRAP_BLOCK_SECONDS),
            "replicates": n_boot,
            "null": "mean paired squared-loss difference equals zero",
            "segments": "blocks never cross session, test fold, or gaps longer than the tested block duration",
            "fdr": "Benjamini-Hochberg over the same four predeclared V3 comparisons, using 15s bootstrap p-values",
        },
        "parameters": {
            "holdout_ratio": holdout_ratio,
            "k_folds": k_folds,
            "purge_rule": "label_end_time < nominal test_start_time",
            "embargo_seconds": embargo_seconds,
            "seed": seed,
            "horizon_seconds": int(df["label_horizon_seconds"].iloc[0]),
        },
        "sample_sizes": {
            "total_clean_sample": n_total,
            "eval_sample": n_eval,
            "holdout_candidate_sample": n_total - split_point,
            "holdout_test_sample_after_embargo": len(test_ho),
            "walk_forward_test_obs": int(test_mask.sum()),
            "walk_forward_folds": len(wf_splits),
        },
        "temporal_audit": {
            "walk_forward_splits": split_audits,
            "holdout": holdout_split["audit"],
            "all_train_labels_end_before_test": all(not x["label_overlap"] for x in split_audits)
            and not holdout_split["audit"]["label_overlap"],
        },
        "walk_forward_comparisons": wf_comparisons,
        "holdout_comparisons": holdout_comparisons,
        "exploratory_c5": c5_exploratory,
        "diagnostic_verdict": diagnostic_verdict,
        "criteria_breakdown": {
            "delta_r2_wf": c1_wf["delta_r2_oos"],
            "delta_min_threshold": FUTILITY_DELTA_MIN,
            "p_fdr_c1": c1_wf["block_bootstrap_p_fdr_adjusted"],
            "folds_positive": f"{c1_wf['folds_positive_count']}/{c1_wf['folds_total']}",
            "delta_r2_holdout": c1_ho["delta_r2_oos_holdout"],
            "p_holdout_c1": c1_ho["block_bootstrap_sensitivity"]["15"]["p_value"],
        },
    }
