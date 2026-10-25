"""Variables del Notebook 001. TODAS causales (usan solo filas <= t) y de ventana FINITA,
de modo que procesar por chunks con solapamiento da EXACTAMENTE el mismo resultado que en bloque.

Grupos
------
BASIC       : mid, spread, volúmenes, profundidad, volatilidad
TRADITIONAL : imbalance, OFI, momentum (baseline B)
LAGS        : rezagos de imbalance (control lineal-temporal, baseline B+)
NAVIER      : velocidad u, dI/dt, gradiente y curvatura de liquidez por nivel, Re_m
Target      : retorno futuro a H segundos (bps y normalizado por volatilidad)

Definiciones "Navier" (OPERACIONALES, no física demostrada):
  u_t        pendiente MCO del log-mid (bps) en los últimos `vel_window` puntos -> bps/s
  dI/dt      [I_suav(t) - I_suav(t-dI_lag)] / dI_lag, con I suavizada por media móvil
  grad_side  pendiente MCO de V_k/mean(V) frente al índice de nivel k (1..10), por lado
  curv_side  coeficiente cuadrático (polinomio ortogonal) de V_k/mean(V) frente a k, por lado
  Re_m       |u| * L / D,  L = profundidad del libro en bps,  D = var. 1 s (bps^2/s)  [adimensional]
"""
from __future__ import annotations

from typing import Iterator

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from .schema import BID_PX, BID_QTY, ASK_PX, ASK_QTY, N_LEVELS, Config, DEFAULT_CONFIG

BASIC = ["spread_bps", "log_vol_bid", "log_vol_ask", "depth_log", "vol60_bps"]   # descriptivo/univariado
# En los MODELOS no entran log_vol_bid/log_vol_ask: junto con depth_log e imb_full son funciones de solo
# (Vb, Va) => colinealidad casi perfecta (VIF 50-180 detectado en el diagnóstico). Se conserva depth_log.
BASIC_MODEL = ["spread_bps", "depth_log", "vol60_bps"]
TRADITIONAL_ONLY = ["imb_full", "imb_top1", "ofi_5", "ret_1", "ret_5", "ret_30"]
LAGS = ["imb_full_lag2", "imb_full_lag5", "imb_full_lag8"]
NAVIER = ["u", "dI_dt", "grad_bid", "grad_ask", "curv_bid", "curv_ask", "re_log"]
NAVIER_EXTRA = ["grad_asym", "grad_sym", "curv_sym"]   # combinaciones lineales: solo análisis univariado
TARGET = "y"          # retorno futuro H / (vol60 * sqrt(H))  (adimensional, ~ z-score)
TARGET_BPS = "y_bps"  # retorno futuro H en bps

# Conjuntos de modelos (anidados)
MODEL_A = BASIC_MODEL
MODEL_B = BASIC_MODEL + TRADITIONAL_ONLY
MODEL_BPLUS = MODEL_B + LAGS
MODEL_C = MODEL_B + NAVIER
MODEL_CPLUS = MODEL_BPLUS + NAVIER

_X = np.arange(1, N_LEVELS + 1) - (N_LEVELS + 1) / 2          # -4.5..4.5
_P1 = _X
_P2 = _X ** 2 - np.mean(_X ** 2)
_SLOPE_W = _P1 / np.sum(_P1 ** 2)
_CURV_W = _P2 / np.sum(_P2 ** 2)


def _ls_slope(y: np.ndarray, w: int) -> np.ndarray:
    """Pendiente MCO en ventana móvil de w puntos (unidades de y por paso). NaN al inicio."""
    xs = np.arange(w) - (w - 1) / 2
    ker = xs / np.sum(xs ** 2)
    out = np.full(len(y), np.nan)
    if len(y) >= w:
        out[w - 1:] = np.convolve(y, ker[::-1], mode="valid")
    return out


def compute_features(raw: pd.DataFrame, cfg: Config = DEFAULT_CONFIG, with_target: bool = True) -> pd.DataFrame:
    """Features a partir de snapshots L2 a 1 s (filas consecutivas = segundos consecutivos)."""
    H = cfg.horizon
    bpx, apx = raw[BID_PX[0]].to_numpy(float), raw[ASK_PX[0]].to_numpy(float)
    mid = (bpx + apx) / 2.0
    bq = raw[BID_QTY].to_numpy(float)
    aq = raw[ASK_QTY].to_numpy(float)
    apx_all = raw[ASK_PX].to_numpy(float)
    bpx_all = raw[BID_PX].to_numpy(float)

    out = pd.DataFrame(index=raw.index)
    out["timestamp"] = raw["timestamp"].to_numpy()
    out["mid"] = mid
    out["spread_bps"] = (apx - bpx) / mid * 1e4

    vb, va = bq.sum(1), aq.sum(1)
    out["vol_bid"], out["vol_ask"] = vb, va
    out["log_vol_bid"], out["log_vol_ask"] = np.log(vb), np.log(va)
    out["depth_log"] = np.log(vb + va)

    logmid_bps = np.log(mid) * 1e4
    r1 = pd.Series(logmid_bps).diff()
    out["vol60_bps"] = r1.rolling(cfg.vol_window).std().to_numpy()

    # --- tradicionales
    imb = (vb - va) / (vb + va)
    out["imb_full"] = imb
    out["imb_top1"] = (bq[:, 0] - aq[:, 0]) / (bq[:, 0] + aq[:, 0])
    # OFI (Cont-Kukanov-Stoikov) sobre snapshots consecutivos, top of book
    pb, pa_ = bpx, apx
    qb, qa = bq[:, 0], aq[:, 0]
    pb0, pa0 = np.r_[np.nan, pb[:-1]], np.r_[np.nan, pa_[:-1]]
    qb0, qa0 = np.r_[np.nan, qb[:-1]], np.r_[np.nan, qa[:-1]]
    e = (np.where(pb >= pb0, qb, 0) - np.where(pb <= pb0, qb0, 0)
         - np.where(pa_ <= pa0, qa, 0) + np.where(pa_ >= pa0, qa0, 0))
    e[0] = np.nan
    top = pd.Series(qb + qa).rolling(cfg.vol_window).mean().to_numpy()
    ofi_raw_5 = pd.Series(e).rolling(cfg.ofi_window).sum().to_numpy()
    out["ofi_raw_5"] = ofi_raw_5
    out["ofi_5"] = ofi_raw_5 / top
    for w in cfg.ret_windows:
        out[f"ret_{w}"] = pd.Series(logmid_bps).diff(w).to_numpy()

    # --- rezagos de imbalance (baseline B+)
    imb_s = pd.Series(imb)
    for L in cfg.imb_lags:
        out[f"imb_full_lag{L}"] = imb_s.shift(L).to_numpy()

    # --- Navier V0.1 (INMUTABLE - Línea base científica)
    out["u"] = _ls_slope(logmid_bps, cfg.vel_window)                       # bps/s
    imb_sm = imb_s.rolling(cfg.imb_smooth).mean()
    out["dI_dt"] = ((imb_sm - imb_sm.shift(cfg.dI_lag)) / cfg.dI_lag).to_numpy()
    norm = np.concatenate([bq, aq], axis=1).mean(1, keepdims=True)
    bn, an = bq / norm, aq / norm
    out["grad_bid"], out["grad_ask"] = bn @ _SLOPE_W, an @ _SLOPE_W
    out["curv_bid"], out["curv_ask"] = bn @ _CURV_W, an @ _CURV_W
    out["grad_asym"] = out["grad_bid"] - out["grad_ask"]
    out["grad_sym"] = 0.5 * (out["grad_bid"] + out["grad_ask"])
    out["curv_sym"] = 0.5 * (out["curv_bid"] + out["curv_ask"])
    L_bps = (apx_all[:, -1] - bpx_all[:, -1]) / mid * 1e4
    D = out["vol60_bps"].to_numpy() ** 2
    re = np.abs(out["u"].to_numpy()) * np.clip(L_bps, 0, None) / D
    out["re_m"] = re
    out["re_log"] = np.log1p(re)

    # --- Hipótesis alternativas V0.2 (Espacio de nombres separado, no altera V0.1)
    # L_vwap dimensional en bps: distancia media de órdenes al mid ponderada por volumen
    l_bid_bps = np.sum(np.abs(mid[:, None] - bpx_all) * bq, axis=1) / np.maximum(vb, 1e-8) / mid * 1e4
    l_ask_bps = np.sum(np.abs(apx_all - mid[:, None]) * aq, axis=1) / np.maximum(va, 1e-8) / mid * 1e4
    out["v02_l_vwap_bps"] = 0.5 * (l_bid_bps + l_ask_bps)

    # Normalización por lado para gradiente y curvatura (desacopla imbalance de forma)
    bn_side = bq / np.maximum(vb[:, None], 1e-8)
    an_side = aq / np.maximum(va[:, None], 1e-8)
    out["v02_grad_bid_norm"] = bn_side @ _SLOPE_W
    out["v02_grad_ask_norm"] = an_side @ _SLOPE_W

    # Reynolds regularizado (suelo épsilon en volatilidad para evitar singularidades)
    eps_vol = 0.05  # 0.05 bps
    d_reg = np.maximum(D, eps_vol ** 2)
    re_v02 = np.abs(out["u"].to_numpy()) * out["v02_l_vwap_bps"].to_numpy() / d_reg
    out["v02_re_log_reg"] = np.log1p(re_v02)

    # --- Hipótesis NAVIER V3: Liquidity-Conditioned Price Impact (namespace v03_)
    # Grupo 1 — Presión y profundidad
    d_ask_k3 = aq[:, :3].sum(axis=1)
    d_bid_k3 = bq[:, :3].sum(axis=1)
    d_ask_k5 = aq[:, :5].sum(axis=1)
    d_bid_k5 = bq[:, :5].sum(axis=1)

    eps_v3 = 1e-6
    d_contra_k3 = np.where(ofi_raw_5 >= 0, d_ask_k3, d_bid_k3)
    d_contra_k5 = np.where(ofi_raw_5 >= 0, d_ask_k5, d_bid_k5)

    out["v03_ofi_raw_5"] = ofi_raw_5
    out["v03_depth_contra_k3"] = d_contra_k3
    out["v03_depth_contra_k5"] = d_contra_k5
    out["v03_pnpc_k3"] = ofi_raw_5 / (d_contra_k3 + eps_v3)
    out["v03_pnpc_k5"] = ofi_raw_5 / (d_contra_k5 + eps_v3)

    # Grupo 2 — Geometría de liquidez
    out["v03_liq_conc_ask"] = aq[:, 0] / (va + eps_v3)
    out["v03_liq_conc_bid"] = bq[:, 0] / (vb + eps_v3)
    liq_conc_contra = np.where(ofi_raw_5 >= 0, out["v03_liq_conc_ask"].to_numpy(), out["v03_liq_conc_bid"].to_numpy())
    out["v03_impact_conc_k3"] = out["v03_pnpc_k3"].to_numpy() * liq_conc_contra

    # Grupo 3 — Dinámica de liquidez (exploratorio H1a, tau = 5s)
    d_ask_mean60 = pd.Series(d_ask_k3).rolling(cfg.vol_window).mean().to_numpy()
    d_bid_mean60 = pd.Series(d_bid_k3).rolling(cfg.vol_window).mean().to_numpy()
    out["v03_depth_replenish_ask"] = pd.Series(d_ask_k3).diff(5).to_numpy() / (d_ask_mean60 + eps_v3)
    out["v03_depth_replenish_bid"] = pd.Series(d_bid_k3).diff(5).to_numpy() / (d_bid_mean60 + eps_v3)

    # Invalidador si existen discontinuidades o excesivo arrastre (si columnas presentes)
    if "state_source" in raw.columns:
        gap_numeric = (raw["state_source"] == "GAP_DISCONTINUITY").astype(int)
        gap_mask = gap_numeric.rolling(cfg.vol_window, min_periods=1).max().to_numpy() == 1
        carried_ratio = (raw["state_source"] == "CARRIED_FORWARD").astype(float).rolling(cfg.vol_window, min_periods=1).mean().to_numpy()
        invalid_history = gap_mask | (carried_ratio > 0.20)
        # Invalidar vol60 y derivadas dinámicas si la ventana histórica está corrompida
        out.loc[invalid_history, ["vol60_bps", "u", "re_m", "re_log", "v02_re_log_reg"]] = np.nan

        # Invalidar variables V3 si hay discontinuidades en su ventana de 5s
        gap5 = gap_numeric.rolling(5, min_periods=1).max().to_numpy() == 1
        out.loc[gap5, ["v03_pnpc_k3", "v03_pnpc_k5", "v03_impact_conc_k3", "v03_depth_replenish_ask", "v03_depth_replenish_bid"]] = np.nan
        # Invalidar reposición si la ventana histórica de 60s está corrompida
        out.loc[invalid_history, ["v03_depth_replenish_ask", "v03_depth_replenish_bid"]] = np.nan

    # --- objetivo (mira al futuro: SOLO etiqueta, nunca feature)
    if with_target:
        fwd = pd.Series(logmid_bps).shift(-H) - pd.Series(logmid_bps)
        target_bps = fwd.to_numpy()
        denom = out["vol60_bps"].to_numpy() * np.sqrt(H)
        # Suelo de volatilidad para el target
        with np.errstate(divide="ignore", invalid="ignore"):
            target_norm = np.where(out["vol60_bps"].to_numpy() >= 0.01, target_bps / denom, np.nan)
        out[TARGET_BPS] = target_bps
        out[TARGET] = target_norm

        if "state_source" in raw.columns:
            # Comprobación causal y exacta en el intervalo futuro (t, t+H]
            gap_numeric = (raw["state_source"] == "GAP_DISCONTINUITY").astype(int)
            gap_future = (
                gap_numeric.iloc[::-1].rolling(H, min_periods=1).max().iloc[::-1].shift(-1).fillna(0).to_numpy() == 1
            )
            if "staleness_ms" in raw.columns:
                stale_series = pd.Series(raw["staleness_ms"].to_numpy())
                stale_at_h = (stale_series.shift(-H) > 1000.0).fillna(False).to_numpy()
                stale_in_future = (
                    (stale_series > 1000.0)
                    .astype(int)
                    .iloc[::-1]
                    .rolling(H, min_periods=1)
                    .max()
                    .iloc[::-1]
                    .shift(-1)
                    .fillna(0)
                    .to_numpy() == 1
                )
                gap_future = gap_future | stale_at_h | stale_in_future
            out.loc[gap_future, [TARGET, TARGET_BPS]] = np.nan

    return out


FEATURE_COLUMNS = (BASIC + TRADITIONAL_ONLY + LAGS + NAVIER + NAVIER_EXTRA)
NAVIER_V02 = ["v02_l_vwap_bps", "v02_grad_bid_norm", "v02_grad_ask_norm", "v02_re_log_reg"]

NAVIER_V3_RATIO = ["v03_pnpc_k3", "v03_pnpc_k5"]
NAVIER_V3_GEOMETRY = ["v03_liq_conc_ask", "v03_liq_conc_bid", "v03_impact_conc_k3"]
NAVIER_V3_CORE = NAVIER_V3_RATIO + NAVIER_V3_GEOMETRY
NAVIER_V3_REPLENISH = ["v03_depth_replenish_ask", "v03_depth_replenish_bid"]
NAVIER_V3 = NAVIER_V3_CORE + NAVIER_V3_REPLENISH
FEATURE_COLUMNS_V3 = FEATURE_COLUMNS + NAVIER_V3



def stream_features(chunks: Iterator[pd.DataFrame], cfg: Config = DEFAULT_CONFIG, feature_cols: list[str] | None = None) -> Iterator[pd.DataFrame]:
    """Procesa el L2 por chunks manteniendo en memoria solo (max_window + H) filas de cola.

    Emite únicamente filas con (a) historia suficiente para todas las ventanas y
    (b) retorno futuro disponible. Es equivalente a compute_features(todo) + dropna().
    """
    H, W = cfg.horizon, cfg.max_window
    cols_to_check = FEATURE_COLUMNS if feature_cols is None else feature_cols
    tail = None
    seq0 = 0           # índice absoluto de la 1ª fila de `tail`
    last_emitted = -1  # índice absoluto de la última fila emitida
    for chunk in chunks:
        chunk = chunk.reset_index(drop=True)
        raw = chunk if tail is None else pd.concat([tail, chunk], ignore_index=True)
        raw.index = np.arange(seq0, seq0 + len(raw))
        feats = compute_features(raw, cfg)
        n = len(raw)
        abs_idx = feats.index.to_numpy()
        valid = feats[cols_to_check + [TARGET, TARGET_BPS]].notna().all(axis=1).to_numpy()
        # no emitir filas cuyo futuro (H filas) aún no está completo
        complete = abs_idx <= (seq0 + n - 1 - H)
        emit = valid & complete & (abs_idx > last_emitted)
        # además: la historia previa debe existir (primeras W filas absolutas se descartan por NaN ya)
        if emit.any():
            res = feats.loc[emit]
            last_emitted = int(res.index.max())
            yield res.reset_index(drop=True)
        keep = min(n, W + H)
        tail = raw.iloc[n - keep:].copy()
        seq0 = seq0 + n - keep


def run_pipeline(source: Iterator[pd.DataFrame], out_path, cfg: Config = DEFAULT_CONFIG) -> dict:
    """Recolector -> features -> parquet (row-groups). Devuelve estadísticas de memoria/filas."""
    writer, rows, max_chunk = None, 0, 0
    for feats in stream_features(source, cfg):
        feats = feats.copy()
        for c in feats.columns:
            if c != "timestamp":
                feats[c] = feats[c].astype("float32") if c != "mid" else feats[c].astype("float64")
        tbl = pa.Table.from_pandas(feats, preserve_index=False)
        if writer is None:
            writer = pq.ParquetWriter(out_path, tbl.schema, compression="zstd")
        writer.write_table(tbl)
        rows += len(feats)
        max_chunk = max(max_chunk, len(feats))
    if writer is not None:
        writer.close()
    return {"rows_out": rows, "max_chunk_rows": max_chunk}
            