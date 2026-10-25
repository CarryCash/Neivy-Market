"""Generar gráficos de la comparativa piloto entre BTC/USDT y BTC/USD."""
import matplotlib.pyplot as plt
import pandas as pd
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
df_usdt = pd.read_parquet(PROJECT_ROOT / "data" / "kraken" / "pilot_btc_usdt_l2_1s.parquet")
df_usd = pd.read_parquet(PROJECT_ROOT / "data" / "kraken" / "pilot_btc_usd_l2_1s.parquet")

# Precios y spread
sp_usdt = (df_usdt["ask_px_1"] - df_usdt["bid_px_1"]) / ((df_usdt["ask_px_1"] + df_usdt["bid_px_1"]) / 2.0) * 10000.0
sp_usd = (df_usd["ask_px_1"] - df_usd["bid_px_1"]) / ((df_usd["ask_px_1"] + df_usd["bid_px_1"]) / 2.0) * 10000.0

nom_usdt = sum(df_usdt[f"bid_px_{i}"] * df_usdt[f"bid_qty_{i}"] + df_usdt[f"ask_px_{i}"] * df_usdt[f"ask_qty_{i}"] for i in range(1, 11)) / 1000.0 # k USD
nom_usd = sum(df_usd[f"bid_px_{i}"] * df_usd[f"bid_qty_{i}"] + df_usd[f"ask_px_{i}"] * df_usd[f"ask_qty_{i}"] for i in range(1, 11)) / 1000.0   # k USD

fig, axes = plt.subplots(3, 1, figsize=(12, 10), sharex=True)

# 1. Spread
axes[0].plot(sp_usdt.values, label="BTC/USDT", color="#f59e0b", alpha=0.8, lw=1.2)
axes[0].plot(sp_usd.values, label="BTC/USD", color="#2563eb", alpha=0.8, lw=1.2)
axes[0].set_ylabel("Spread (bps)")
axes[0].set_title("Ensayo Piloto Simultáneo (15 min / 900 s) — Comparativa L2 en Kraken WS v2")
axes[0].legend(loc="upper right")
axes[0].grid(True, alpha=0.3)

# 2. Profundidad
axes[1].plot(nom_usdt.values, label="BTC/USDT (k USDT)", color="#f59e0b", alpha=0.8, lw=1.2)
axes[1].plot(nom_usd.values, label="BTC/USD (k USD)", color="#2563eb", alpha=0.8, lw=1.2)
axes[1].set_ylabel("Profundidad 10 Niveles (Miles de USD)")
axes[1].legend(loc="upper right")
axes[1].grid(True, alpha=0.3)

# 3. Updates por segundo
axes[2].plot(df_usdt["updates_count"].values, label="BTC/USDT", color="#f59e0b", alpha=0.7, lw=1.0)
axes[2].plot(df_usd["updates_count"].values, label="BTC/USD", color="#2563eb", alpha=0.7, lw=1.0)
axes[2].set_ylabel("Updates / segundo")
axes[2].set_xlabel("Tiempo relativo (segundos)")
axes[2].legend(loc="upper right")
axes[2].grid(True, alpha=0.3)

plt.tight_layout()
out_fig = PROJECT_ROOT / "figures" / "pilot_pair_comparison_15min.png"
out_fig.parent.mkdir(exist_ok=True)
plt.savefig(out_fig, dpi=150)
print(f"Gráfico guardado en {out_fig}")
