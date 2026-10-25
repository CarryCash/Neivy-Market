"""NAVIER V2 — Fase 1: Análisis comparativo reproducible entre BTC/USDT y BTC/USD."""
from __future__ import annotations

import json
from pathlib import Path
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]

def load_data():
    usdt_p = PROJECT_ROOT / "data" / "kraken" / "pilot_btc_usdt_l2_1s.parquet"
    usd_p = PROJECT_ROOT / "data" / "kraken" / "pilot_btc_usd_l2_1s.parquet"
    usdt_m = PROJECT_ROOT / "data" / "kraken" / "pilot_btc_usdt_l2.parquet.manifest.json"
    usd_m = PROJECT_ROOT / "data" / "kraken" / "pilot_btc_usd_l2.parquet.manifest.json"
    
    df_usdt = pd.read_parquet(usdt_p)
    df_usd = pd.read_parquet(usd_p)
    m_usdt = json.loads(usdt_m.read_text(encoding="utf-8"))
    m_usd = json.loads(usd_m.read_text(encoding="utf-8"))
    return df_usdt, df_usd, m_usdt, m_usd

def compute_metrics(df: pd.DataFrame, manifest: dict, name: str) -> dict:
    valid_mask = df["state_source"] != "GAP_DISCONTINUITY"
    
    # Precios y spread
    bpx1 = df["bid_px_1"]
    apx1 = df["ask_px_1"]
    mid = (bpx1 + apx1) / 2.0
    spread_bps = (apx1 - bpx1) / mid * 10000.0
    
    # Profundidad nominal (Quote) y en BTC
    bid_nom = sum(df[f"bid_px_{i}"] * df[f"bid_qty_{i}"] for i in range(1, 11))
    ask_nom = sum(df[f"ask_px_{i}"] * df[f"ask_qty_{i}"] for i in range(1, 11))
    tot_nom = bid_nom + ask_nom
    
    bid_qty = sum(df[f"bid_qty_{i}"] for i in range(1, 11))
    ask_qty = sum(df[f"ask_qty_{i}"] for i in range(1, 11))
    tot_qty = bid_qty + ask_qty
    
    total_sec = len(df)
    state_counts = df["state_source"].value_counts().to_dict()
    obs_sec = int(state_counts.get("OBSERVED", 0))
    car_sec = int(state_counts.get("CARRIED_FORWARD", 0))
    gap_sec = int(state_counts.get("GAP_DISCONTINUITY", 0))
    
    # Segundos utilizables bajo criterio estricto:
    # 1. Sin GAP_DISCONTINUITY (nivel del libro presente)
    # 2. Staleness <= 1000 ms (estado actualizado recientemente, no obsoleto)
    usable_strict = int(((df["state_source"] != "GAP_DISCONTINUITY") & (df["staleness_ms"] <= 1000.0)).sum())
    # Criterio estándar (resampler): OBSERVED + CARRIED_FORWARD con staleness <= 3000 ms
    usable_standard = int(valid_mask.sum())
    
    sp_valid = spread_bps[valid_mask]
    
    return {
        "symbol": name,
        "manifest": {
            "elapsed_seconds": manifest.get("elapsed_seconds"),
            "valid_rows_raw": manifest.get("valid_rows_written"),
            "messages": manifest.get("adapter_counters", {}).get("messages"),
            "valid_updates": manifest.get("adapter_counters", {}).get("valid_updates"),
            "checksum_failures": manifest.get("adapter_counters", {}).get("checksum_failures"),
            "malformed_messages": manifest.get("adapter_counters", {}).get("malformed_messages"),
            "ignored_messages": manifest.get("adapter_counters", {}).get("ignored_messages"),
            "reconnects": manifest.get("adapter_counters", {}).get("reconnects"),
            "final_status": manifest.get("final_book_status"),
        },
        "seconds": {
            "total": total_sec,
            "observed": obs_sec,
            "observed_pct": round(obs_sec / total_sec * 100.0, 2),
            "carried_forward": car_sec,
            "carried_forward_pct": round(car_sec / total_sec * 100.0, 2),
            "gap_discontinuity": gap_sec,
            "gap_discontinuity_pct": round(gap_sec / total_sec * 100.0, 2),
            "usable_standard_sec": usable_standard,
            "usable_standard_pct": round(usable_standard / total_sec * 100.0, 2),
            "usable_strict_sec": usable_strict,
            "usable_strict_pct": round(usable_strict / total_sec * 100.0, 2),
        },
        "spread_bps": {
            "mean": round(float(sp_valid.mean()), 4),
            "std": round(float(sp_valid.std()), 4),
            "median": round(float(sp_valid.median()), 4),
            "p05": round(float(sp_valid.quantile(0.05)), 4),
            "p25": round(float(sp_valid.quantile(0.25)), 4),
            "p75": round(float(sp_valid.quantile(0.75)), 4),
            "p95": round(float(sp_valid.quantile(0.95)), 4),
            "p99": round(float(sp_valid.quantile(0.99)), 4),
            "min": round(float(sp_valid.min()), 4),
            "max": round(float(sp_valid.max()), 4),
        },
        "depth_nominal_quote": {
            "mean": round(float(tot_nom[valid_mask].mean()), 2),
            "median": round(float(tot_nom[valid_mask].median()), 2),
            "p05": round(float(tot_nom[valid_mask].quantile(0.05)), 2),
            "p95": round(float(tot_nom[valid_mask].quantile(0.95)), 2),
            "bid_mean": round(float(bid_nom[valid_mask].mean()), 2),
            "ask_mean": round(float(ask_nom[valid_mask].mean()), 2),
        },
        "depth_btc": {
            "mean": round(float(tot_qty[valid_mask].mean()), 4),
            "median": round(float(tot_qty[valid_mask].median()), 4),
            "p05": round(float(tot_qty[valid_mask].quantile(0.05)), 4),
            "p95": round(float(tot_qty[valid_mask].quantile(0.95)), 4),
            "bid_mean": round(float(bid_qty[valid_mask].mean()), 4),
            "ask_mean": round(float(ask_qty[valid_mask].mean()), 4),
        },
        "updates_per_second": {
            "mean": round(float(df["updates_count"].mean()), 2),
            "std": round(float(df["updates_count"].std()), 2),
            "median": round(float(df["updates_count"].median()), 2),
            "p75": round(float(df["updates_count"].quantile(0.75)), 2),
            "p95": round(float(df["updates_count"].quantile(0.95)), 2),
            "p99": round(float(df["updates_count"].quantile(0.99)), 2),
            "max": int(df["updates_count"].max()),
        },
        "staleness_ms": {
            "mean": round(float(df["staleness_ms"].dropna().mean()), 2),
            "median": round(float(df["staleness_ms"].dropna().median()), 2),
            "p75": round(float(df["staleness_ms"].dropna().quantile(0.75)), 2),
            "p95": round(float(df["staleness_ms"].dropna().quantile(0.95)), 2),
            "p99": round(float(df["staleness_ms"].dropna().quantile(0.99)), 2),
            "max": round(float(df["staleness_ms"].dropna().max()), 2),
        }
    }

def main():
    df_usdt, df_usd, m_usdt, m_usd = load_data()
    res_usdt = compute_metrics(df_usdt, m_usdt, "BTC/USDT")
    res_usd = compute_metrics(df_usd, m_usd, "BTC/USD")
    
    # Diferencias pareadas en la ventana simultánea de 898 segundos
    aligned = pd.merge(
        df_usdt[["timestamp", "bid_px_1", "ask_px_1", "updates_count", "staleness_ms", "state_source"]],
        df_usd[["timestamp", "bid_px_1", "ask_px_1", "updates_count", "staleness_ms", "state_source"]],
        on="timestamp",
        suffixes=("_usdt", "_usd")
    )
    
    valid_paired = (aligned["state_source_usdt"] != "GAP_DISCONTINUITY") & (aligned["state_source_usd"] != "GAP_DISCONTINUITY")
    
    sp_usdt = (aligned["ask_px_1_usdt"] - aligned["bid_px_1_usdt"]) / ((aligned["ask_px_1_usdt"] + aligned["bid_px_1_usdt"])/2.0) * 10000.0
    sp_usd = (aligned["ask_px_1_usd"] - aligned["bid_px_1_usd"]) / ((aligned["ask_px_1_usd"] + aligned["bid_px_1_usd"])/2.0) * 10000.0
    diff_spread = sp_usd[valid_paired] - sp_usdt[valid_paired]
    diff_updates = aligned["updates_count_usd"] - aligned["updates_count_usdt"]
    diff_staleness = aligned["staleness_ms_usd"][valid_paired] - aligned["staleness_ms_usdt"][valid_paired]
    
    paired_summary = {
        "aligned_seconds": len(aligned),
        "mutually_valid_seconds": int(valid_paired.sum()),
        "spread_diff_usd_minus_usdt_bps": {
            "mean": round(float(diff_spread.mean()), 4),
            "median": round(float(diff_spread.median()), 4),
            "p05": round(float(diff_spread.quantile(0.05)), 4),
            "p95": round(float(diff_spread.quantile(0.95)), 4),
        },
        "updates_diff_usd_minus_usdt": {
            "mean": round(float(diff_updates.mean()), 2),
            "median": round(float(diff_updates.median()), 2),
            "usd_higher_count": int((diff_updates > 0).sum()),
            "usd_higher_pct": round(float((diff_updates > 0).mean() * 100.0), 2),
        },
        "staleness_diff_usd_minus_usdt_ms": {
            "mean": round(float(diff_staleness.mean()), 2),
            "median": round(float(diff_staleness.median()), 2),
        }
    }
    
    full_output = {
        "BTC_USDT": res_usdt,
        "BTC_USD": res_usd,
        "paired_comparison": paired_summary
    }
    
    out_file = PROJECT_ROOT / "results" / "pilot_pair_comparison_results.json"
    out_file.write_text(json.dumps(full_output, indent=2), encoding="utf-8")
    print(json.dumps(full_output, indent=2))

if __name__ == "__main__":
    main()
