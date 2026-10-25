"""Generador de L2 sintético con VERDAD CONOCIDA.

Tres "mundos" para validar el pipeline (no el mercado):

S0_noise      : el retorno futuro es ruido puro (sin señal de ningún tipo).
                -> Nada debe salir significativo (calibración de falsos positivos).
S1_traditional: el retorno depende SOLO de una variable "tradicional" latente (el flujo f,
                que se manifiesta como imbalance). Las variables tipo-Navier se derivan del mismo
                libro (correlacionadas con f) pero NO tienen información propia.
                -> Deben salir señales univariadas, pero el aporte INCREMENTAL de Navier debe ser nulo.
S2_navier     : como S1 + una señal plantada en dos latentes "de fluido":
                  * tau : inclinación asimétrica de la liquidez por nivel (gradiente)
                  * aceleración del flujo (f_t - f_{t-5})
                -> El aporte incremental de Navier debe detectarse.
                NOTA HONESTA: la magnitud (c_tau=0.08, c_acc=0.24) se fijó tras un barrido de potencia como
                la señal a partir de la cual los 4 criterios pre-registrados se cumplen con ~28 h de datos.
                Con 1/4 de esa magnitud el pipeline NO la detecta (ver curva de potencia en el notebook).

IMPORTANTE: esto valida la TUBERÍA (que detecte lo que existe y no invente lo que no existe).
No dice nada sobre si el mercado real contiene esta señal.
El generador NO comparte código con features.py: los latentes se observan solo a través del libro.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from scipy.signal import lfilter

from .schema import BID_PX, BID_QTY, ASK_PX, ASK_QTY, N_LEVELS, RAW_COLUMNS

TICK = 0.1
P0 = 60_000.0
SYNTH_T0 = pd.Timestamp("2000-01-01 00:00:00", tz="UTC")  # fecha deliberadamente falsa

SCENARIOS = {
    #                  c_f    c_tau  c_acc   (efecto por segundo, en unidades de sigma_t)
    "S0_noise":       dict(c_f=0.00, c_tau=0.00, c_acc=0.00),
    "S1_traditional": dict(c_f=0.02, c_tau=0.00, c_acc=0.00),
    "S2_navier":      dict(c_f=0.02, c_tau=0.08, c_acc=0.24),
}

GAMMA = 0.35   # cuánto desplaza f el log-volumen de bid/ask
DELTA = 0.50   # cuánto inclina tau el perfil de liquidez por nivel
LEVEL_NOISE = 0.35


def _ar1(n: int, phi: float, rng, shape_tail=()) -> np.ndarray:
    e = rng.standard_normal((n,) + shape_tail)
    return lfilter([np.sqrt(1 - phi ** 2)], [1, -phi], e, axis=0)


def generate(scenario: str, n: int = 100_000, seed: int = 7, navier_scale: float = 1.0) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Devuelve (raw_l2, latentes). `latentes` es la verdad oculta (solo para auditoría).
    navier_scale multiplica la señal plantada Navier (c_tau, c_acc) -> para curvas de potencia."""
    p = dict(SCENARIOS[scenario])
    p["c_tau"] *= navier_scale
    p["c_acc"] *= navier_scale
    rng = np.random.default_rng(seed)

    f = _ar1(n, 0.98, rng)          # flujo lento
    tau = _ar1(n, 0.97, rng)        # inclinación de liquidez
    logsig = np.log(1.0e-4) + 0.30 * _ar1(n, 0.9995, rng)
    sigma = np.exp(logsig)

    # ---- retornos: r[t+1] depende de los latentes en t (sin lookahead dentro del generador)
    eps = rng.standard_t(5, n) / np.sqrt(5 / 3)          # colas pesadas, var unitaria
    f_lag5 = np.concatenate([np.zeros(5), f[:-5]])
    drive = p["c_f"] * f + p["c_tau"] * tau + p["c_acc"] * (f - f_lag5)
    r = np.zeros(n)
    r[1:] = sigma[1:] * (eps[1:] + drive[:-1])
    logmid = np.log(P0) + np.cumsum(r)
    mid = np.exp(logmid)

    # ---- precios del libro (cuantizados a tick)
    spread_ticks = 1 + rng.poisson(0.5 * sigma / 1e-4)
    best_bid = np.floor((mid - spread_ticks * TICK / 2) / TICK) * TICK
    best_ask = best_bid + spread_ticks * TICK
    gaps = 1 + rng.geometric(0.5, (n, N_LEVELS - 1)) - 1  # >=1 tick, media 2
    cum = np.concatenate([np.zeros((n, 1)), np.cumsum(gaps, axis=1)], axis=1) * TICK
    bid_px = best_bid[:, None] - cum
    ask_px = best_ask[:, None] + np.concatenate(
        [np.zeros((n, 1)), np.cumsum(1 + rng.geometric(0.5, (n, N_LEVELS - 1)) - 1, axis=1)], axis=1) * TICK

    # ---- volúmenes (lognormales; f desplaza bid vs ask; tau inclina el perfil por nivel)
    k = np.arange(1, N_LEVELS + 1)
    base = 0.5 * (1 + 0.12 * (k - 1))
    z = (k - 5.5) / 4.5
    eta_b = LEVEL_NOISE * _ar1(n, 0.9, rng, (N_LEVELS,))
    eta_a = LEVEL_NOISE * _ar1(n, 0.9, rng, (N_LEVELS,))
    bid_qty = base * np.exp(GAMMA * f[:, None] + DELTA * tau[:, None] * z + eta_b)
    ask_qty = base * np.exp(-GAMMA * f[:, None] - DELTA * tau[:, None] * z + eta_a)

    ts = pd.date_range(SYNTH_T0, periods=n, freq="1s")
    cols = {"timestamp": ts}
    for j in range(N_LEVELS):
        cols[BID_PX[j]] = bid_px[:, j]
    for j in range(N_LEVELS):
        cols[BID_QTY[j]] = bid_qty[:, j].astype("float32")
    for j in range(N_LEVELS):
        cols[ASK_PX[j]] = ask_px[:, j]
    for j in range(N_LEVELS):
        cols[ASK_QTY[j]] = ask_qty[:, j].astype("float32")
    raw = pd.DataFrame(cols)[RAW_COLUMNS]
    latent = pd.DataFrame({"timestamp": ts, "f": f, "tau": tau, "sigma": sigma})
    return raw, latent


def write_parquet(df: pd.DataFrame, path, chunk_rows: int = 20_000) -> None:
    """Escribe por row-groups (misma mecánica que usará el recolector real)."""
    writer = None
    for i in range(0, len(df), chunk_rows):
        tbl = pa.Table.from_pandas(df.iloc[i:i + chunk_rows], preserve_index=False)
        if writer is None:
            writer = pq.ParquetWriter(path, tbl.schema, compression="zstd")
        writer.write_table(tbl)
    writer.close()


def build_all(out_dir, n: int = 100_000, seed: int = 7) -> dict:
    """Genera los 3 mundos. Misma semilla => mismo ruido base; sólo cambia la señal plantada."""
    from pathlib import Path
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    paths = {}
    for name in SCENARIOS:
        raw, latent = generate(name, n=n, seed=seed)
        write_parquet(raw, out / f"raw_{name}.parquet")
        latent.to_parquet(out / f"latent_{name}.parquet", index=False)
        paths[name] = out / f"raw_{name}.parquet"
    return paths
