"""Gráficos del Notebook 001 (guardan PNG en figures/ y devuelven la figura)."""
from __future__ import annotations

import pathlib
import numpy as np
import pandas as pd
import matplotlib
import matplotlib.pyplot as plt
from scipy import stats

from . import features as F, analysis as A
from .schema import N_LEVELS, BID_QTY, ASK_QTY

FIG_DIR = pathlib.Path(__file__).resolve().parents[1] / "figures"
FIG_DIR.mkdir(exist_ok=True)
SC_COL = {"S0_noise": "#7f7f7f", "S1_traditional": "#1f77b4", "S2_navier": "#d95f02"}
GRP_COL = {"basic": "#8c8c8c", "trad": "#1f77b4", "lag": "#7fb3e6", "navier": "#d95f02"}
plt.rcParams.update({"figure.dpi": 110, "axes.grid": True, "grid.alpha": .25, "axes.spines.top": False,
                     "axes.spines.right": False, "font.size": 9})


def group_of(f: str) -> str:
    if f in F.NAVIER or f in F.NAVIER_EXTRA: return "navier"
    if f in F.LAGS: return "lag"
    if f in F.TRADITIONAL_ONLY: return "trad"
    return "basic"


def _save(fig, name):
    fig.savefig(FIG_DIR / f"{name}.png", bbox_inches="tight")
    return fig


def fig_overview(df, raw, name="fig01_overview"):
    """Serie temporal, libro y estructura por nivel. `raw` = un chunk (row-group) del L2 crudo."""
    fig, ax = plt.subplots(2, 2, figsize=(12, 7))
    ts0 = raw["timestamp"].iloc[0] + pd.Timedelta("100s")
    w = df[(df["timestamp"] >= ts0) & (df["timestamp"] < ts0 + pd.Timedelta("600s"))]
    t = np.arange(len(w))
    ax[0, 0].plot(t, w["mid"], lw=1); ax[0, 0].set_title("Mid-price (600 s)"); ax[0, 0].set_ylabel("USDT (sintético)")
    a = ax[0, 1]; a.plot(t, w["imb_full"], lw=1, label="imbalance I"); a.set_title("Imbalance y su derivada temporal")
    a2 = a.twinx(); a2.plot(t, w["dI_dt"], color="#d95f02", lw=.8, alpha=.8, label="dI/dt"); a2.grid(False)
    a.set_ylabel("I"); a2.set_ylabel("dI/dt", color="#d95f02")
    k = np.arange(1, N_LEVELS + 1)
    b = raw[BID_QTY].to_numpy(float); s = raw[ASK_QTY].to_numpy(float)
    for arr, lab, c in [(b, "bid", "#2ca02c"), (s, "ask", "#d62728")]:
        ax[1, 0].errorbar(k, arr.mean(0), arr.std(0), label=lab, color=c, capsize=2, marker="o", ms=3)
    ax[1, 0].set_title("Perfil medio de liquidez por nivel (±1 sd)"); ax[1, 0].set_xlabel("nivel del libro k"); ax[1, 0].legend()
    seg = raw[BID_QTY].iloc[100:400].to_numpy(float).T
    im = ax[1, 1].imshow(np.log(seg), aspect="auto", cmap="viridis")
    ax[1, 1].set_title("log(volumen bid) por nivel — 300 s"); ax[1, 1].set_xlabel("segundos"); ax[1, 1].set_ylabel("nivel k")
    ax[1, 1].grid(False); fig.colorbar(im, ax=ax[1, 1], fraction=.04)
    fig.tight_layout()
    return _save(fig, name)


def fig_distributions(df, name="fig02_distributions"):
    cols = ["spread_bps", "imb_full", "ofi_5", "vol60_bps", "u", "dI_dt", "grad_asym", "curv_sym", "re_log", "ret_5", "depth_log", "y"]
    fig, ax = plt.subplots(3, 4, figsize=(13, 7.5))
    for a, c in zip(ax.ravel(), cols):
        x = df[c].to_numpy(float)
        lo, hi = np.percentile(x, [.5, 99.5])
        a.hist(x[(x >= lo) & (x <= hi)], bins=60, color=GRP_COL[group_of(c)] if c != "y" else "k", alpha=.8)
        a.set_title(f"{c}\nskew={stats.skew(x):.2f}  kurt={stats.kurtosis(x):.1f}", fontsize=8.5)
    fig.suptitle("Distribuciones (recortadas al 0.5–99.5%). Naranja = Navier, azul = tradicional, gris = básicas", y=1.0)
    fig.tight_layout()
    return _save(fig, name)


def fig_corr(df, name="fig03_correlation"):
    cols = F.FEATURE_COLUMNS + [F.TARGET]
    C = df[cols].corr(method="spearman")
    fig, ax = plt.subplots(figsize=(11, 9))
    im = ax.imshow(C, cmap="RdBu_r", vmin=-1, vmax=1); ax.grid(False)
    ax.set_xticks(range(len(cols))); ax.set_xticklabels(cols, rotation=90); ax.set_yticks(range(len(cols))); ax.set_yticklabels(cols)
    for lab in ax.get_xticklabels() + ax.get_yticklabels():
        lab.set_color(GRP_COL[group_of(lab.get_text())] if lab.get_text() != F.TARGET else "k")
    fig.colorbar(im, fraction=.04); ax.set_title("Correlación de Spearman entre variables (última fila/col = retorno futuro y)")
    fig.tight_layout()
    return _save(fig, name)


def fig_acf(df, H, name="fig04_autocorrelation"):
    cols = ["imb_full", "dI_dt", "grad_asym", "u", "vol60_bps", "ofi_5", "y"]
    lags = np.arange(1, 101)
    fig, ax = plt.subplots(figsize=(9, 4.5))
    for c in cols:
        x = df[c].to_numpy(float); x = x - x.mean()
        v = x @ x
        ax.plot(lags, [x[l:] @ x[:-l] / v for l in lags], label=c, lw=1.4)
    ax.axvline(H, color="k", ls=":", lw=.8); ax.text(H + 1, .9, f"H={H}", fontsize=8)
    ax.set_xlabel("rezago (s)"); ax.set_ylabel("autocorrelación"); ax.legend(ncol=4, fontsize=8)
    ax.set_title("Persistencia de las variables => pocas observaciones efectivamente independientes")
    fig.tight_layout()
    return _save(fig, name)


def fig_deciles(dfs: dict, H, feats=("imb_full", "grad_asym", "dI_dt"), name="fig05_deciles"):
    fig, ax = plt.subplots(len(dfs), len(feats), figsize=(11, 2.9 * len(dfs)), sharex="col")
    for i, (sc, df) in enumerate(dfs.items()):
        for j, f in enumerate(feats):
            d = A.decile_table(df, f, H)
            ax[i, j].errorbar(d["bin"], d["mean_y"], 2 * d["se"], fmt="o-", color=SC_COL[sc], capsize=2, ms=4)
            ax[i, j].axhline(0, color="k", lw=.6)
            if i == 0: ax[i, j].set_title(f)
            if j == 0: ax[i, j].set_ylabel(f"{sc}\nE[y | decil]")
            if i == len(dfs) - 1: ax[i, j].set_xlabel("decil de la variable")
    fig.suptitle("Retorno futuro (normalizado) medio por decil, ±2 EE-HAC", y=1.0)
    fig.tight_layout()
    return _save(fig, name)


def fig_forest(tables: dict, name="fig06_forest"):
    feats = F.FEATURE_COLUMNS
    fig, ax = plt.subplots(1, len(tables), figsize=(4.3 * len(tables), 8), sharey=True)
    for a, (sc, t) in zip(np.atleast_1d(ax), tables.items()):
        t = t.set_index("feature").loc[feats][::-1]
        se = t["pearson"] / t["t_hac"]
        colors = [GRP_COL[group_of(f)] for f in t.index]
        a.errorbar(t["pearson"], range(len(t)), xerr=1.96 * se.abs(), fmt="none", ecolor="#bbb", capsize=2)
        a.scatter(t["pearson"], range(len(t)), c=colors, s=28, zorder=3, edgecolor=["k" if q < .05 else "none" for q in t["q_perm"]])
        a.axvline(0, color="k", lw=.7); a.set_title(sc, color=SC_COL[sc]); a.set_xlabel("corr(x, y)  [IC95% HAC]")
        a.set_yticks(range(len(t))); a.set_yticklabels(t.index)
    fig.suptitle("Relación univariada con el retorno futuro. Borde negro = significativo con FDR 5% (permutación circular)", y=1.0)
    fig.tight_layout()
    return _save(fig, name)


def fig_calibration(x, y, H, name="fig07_calibration"):
    cal = A.calibration_check(x, y, H, n_shifts=400)
    ts = cal["t_values"]
    fig, ax = plt.subplots(1, 2, figsize=(10, 3.8))
    ax[0].hist(ts, bins=30, density=True, alpha=.7); g = np.linspace(-4, 4, 200); ax[0].plot(g, stats.norm.pdf(g), "k")
    ax[0].set_title(f"t-HAC bajo hipótesis nula (x desplazada)\nrechazo@5% = {100 * cal['reject_5pct']:.1f}%  (ideal 5%),  sd(t) = {cal['t_sd']:.2f} (ideal 1)")
    stats.probplot(ts, dist="norm", plot=ax[1]); ax[1].set_title("QQ-plot vs Normal")
    fig.tight_layout(); _save(fig, name)
    return fig, cal


def fig_information(uni_oos, mi, add1, name="fig08_information"):
    fig, ax = plt.subplots(1, 3, figsize=(14, 6), sharey=True)
    feats = F.FEATURE_COLUMNS[::-1]
    cols = [GRP_COL[group_of(f)] for f in feats]
    u = uni_oos.set_index("feature").loc[feats]; m = mi.set_index("feature").loc[feats]
    a1 = add1.set_index("feature").reindex(feats)
    ax[0].barh(feats, u["oos_r2"] * 100, color=cols); ax[0].set_title("R² OOS univariado (%)\n(walk-forward)"); ax[0].axvline(0, color="k", lw=.6)
    ax[1].barh(feats, m["mi_excess"], xerr=m["mi_null_sd"], color=cols); ax[1].set_title("Información mutua en exceso\nvs. nula (nats, ±1 sd nula)"); ax[1].axvline(0, color="k", lw=.6)
    ax[2].barh(feats, a1["delta_r2"].fillna(0) * 100, color=cols); ax[2].set_title("ΔR² OOS al AÑADIR a B+ (%)\n(aporte incremental individual)"); ax[2].axvline(0, color="k", lw=.6)
    fig.tight_layout()
    return _save(fig, name)


def fig_nested(results: dict, name="fig09_nested"):
    n = len(results)
    fig, ax = plt.subplots(2, n, figsize=(4.6 * n, 7))
    for j, (sc, r) in enumerate(results.items()):
        names = list(r["r2"].keys())
        ax[0, j].bar(range(len(names)), [100 * r["r2"][k] for k in names], color=[SC_COL[sc]] * len(names), alpha=.85)
        ax[0, j].set_xticks(range(len(names))); ax[0, j].set_xticklabels([k.split()[0] for k in names])
        ax[0, j].set_title(f"{sc}\nR² OOS por modelo (%)", color=SC_COL[sc]); ax[0, j].axhline(0, color="k", lw=.6)
        ax[1, j].hist(100 * r["placebo"], bins=25, color="#bbb", edgecolor="w")
        ax[1, j].axvline(100 * r["delta_r2"], color="crimson", lw=2, label=f"real: {100 * r['delta_r2']:.3f}%")
        ax[1, j].set_title(f"ΔR²(C+ − B+) real vs. placebo\np_placebo = {r['p_placebo']:.3f}   Wald p = {r['wald']['p']:.1e}")
        ax[1, j].set_xlabel("ΔR² OOS (%)"); ax[1, j].legend()
    fig.tight_layout()
    return _save(fig, name)


def fig_power(table: pd.DataFrame, name="fig10_power"):
    fig, ax = plt.subplots(1, 3, figsize=(14, 3.8))
    ax[0].plot(table["fraction"], 100 * table["delta_r2"], "o-", color=SC_COL["S2_navier"]); ax[0].axhline(0, color="k", lw=.6)
    ax[0].set_title("ΔR² OOS (C+ − B+) vs. magnitud de la señal plantada"); ax[0].set_ylabel("%"); ax[0].set_xlabel("fracción de la señal S2")
    ax[1].semilogy(table["fraction"], table["wald_p"], "o-", label="Wald-HAC"); ax[1].semilogy(table["fraction"], table["dm_p"], "s-", label="DM")
    ax[1].axhline(.01, color="crimson", ls="--", lw=1); ax[1].set_title("p-valores (línea = α 1%)"); ax[1].legend(); ax[1].set_xlabel("fracción de la señal S2")
    ax[2].bar(table["fraction"].astype(str), table["signal"].astype(int), color=np.where(table["signal"], "seagreen", "#c66"))
    ax[2].set_title("Veredicto (1 = señal detectada)"); ax[2].set_xlabel("fracción de la señal S2")
    fig.tight_layout()
    return _save(fig, name)


def fig_mc(mc: pd.DataFrame, name="fig11_false_positives"):
    fig, ax = plt.subplots(1, 2, figsize=(11, 3.8))
    for sc, d in mc.groupby("scenario"):
        ax[0].hist(d["wald_p"], bins=np.linspace(0, 1, 11), alpha=.6, label=sc, color=SC_COL[sc])
    ax[0].set_title("p-valor Wald-HAC del bloque Navier (mundos SIN señal Navier)\nbajo H0 debería ser ~uniforme"); ax[0].legend(); ax[0].set_xlabel("p")
    crit = mc.groupby("scenario")[["c1_wald", "c2_dm", "c3_folds", "c4_placebo", "signal"]].mean() * 100
    crit.T.plot.bar(ax=ax[1], color=[SC_COL[c] for c in crit.index]); ax[1].set_ylabel("% de corridas que cumplen"); ax[1].set_title("Tasa de 'falsos positivos' por criterio")
    ax[1].set_xticklabels(["Wald", "DM", "folds", "placebo", "TODOS"], rotation=0)
    fig.tight_layout()
    return _save(fig, name)
