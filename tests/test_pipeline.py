"""Pruebas de integridad. Ejecutar:  python tests/test_pipeline.py   (o pytest)"""
import sys, tempfile, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import numpy as np, pandas as pd
from navier_lab import synthetic as S, features as F, collector as C
from navier_lab.schema import DEFAULT_CONFIG as CFG, BID_QTY

RAW, _ = S.generate("S2_navier", n=12_000, seed=3)


def test_no_lookahead():
    """Cambiar el FUTURO (filas > t0) no debe alterar ninguna feature en filas <= t0."""
    t0 = 6_000
    a = F.compute_features(RAW, CFG, with_target=False)
    mod = RAW.copy()
    rng = np.random.default_rng(0)
    for c in mod.columns:
        if c != "timestamp":
            noise = (1 + 0.05 * rng.standard_normal(len(mod) - t0 - 1)).clip(0.5, 1.5)
            mod.loc[t0 + 1:, c] = (mod.loc[t0 + 1:, c].to_numpy(float) * noise).astype(mod[c].dtype)
    b = F.compute_features(mod, CFG, with_target=False)
    cols = [c for c in F.FEATURE_COLUMNS if c != "mid"] + ["mid"]
    diff = np.nanmax(np.abs(a.loc[:t0, cols].to_numpy(float) - b.loc[:t0, cols].to_numpy(float)))
    assert diff < 1e-9, f"lookahead detectado: {diff}"


def test_target_is_future_only():
    """El target en t debe coincidir con log(mid[t+H]/mid[t]) y ninguna feature debe igualarlo."""
    a = F.compute_features(RAW, CFG)
    H = CFG.horizon
    manual = 1e4 * (np.log(a["mid"].shift(-H)) - np.log(a["mid"]))
    assert np.allclose(manual.dropna(), a[F.TARGET_BPS].dropna(), atol=1e-4)
    for c in F.FEATURE_COLUMNS:
        m = a[[c, F.TARGET_BPS]].dropna()
        assert abs(np.corrcoef(m[c], m[F.TARGET_BPS])[0, 1]) < 0.5, f"{c} sospechosamente correlada con el futuro"


def test_streaming_equals_batch():
    """Procesar en chunks de tamaños raros == procesar todo junto (tras dropna)."""
    full = F.compute_features(RAW, CFG)
    cols = F.FEATURE_COLUMNS + [F.TARGET, F.TARGET_BPS]
    full = full.dropna(subset=cols).reset_index(drop=True)
    for chunk_rows in (997, 2_500, 5_000):
        chunks = (RAW.iloc[i:i + chunk_rows] for i in range(0, len(RAW), chunk_rows))
        got = pd.concat(list(F.stream_features(chunks, CFG)), ignore_index=True)
        assert len(got) == len(full), (chunk_rows, len(got), len(full))
        assert (got["timestamp"].to_numpy() == full["timestamp"].to_numpy()).all()
        d = np.nanmax(np.abs(got[cols].to_numpy(float) - full[cols].to_numpy(float)))
        assert d < 1e-9, f"chunks={chunk_rows} difiere {d}"


def test_validation_catches_bad_data():
    bad = RAW.iloc[:100].copy(); bad.loc[10, "ask_px_1"] = bad.loc[10, "bid_px_1"] - 1
    try: C.validate_chunk(bad); raise SystemExit("no detectó libro cruzado")
    except ValueError: pass
    gap = RAW.iloc[:100].drop(index=[50]); 
    try: C.validate_chunk(gap); raise SystemExit("no detectó hueco")
    except ValueError: pass
    neg = RAW.iloc[:100].copy(); neg.loc[5, BID_QTY[2]] = 0
    try: C.validate_chunk(neg); raise SystemExit("no detectó qty<=0")
    except ValueError: pass


def test_regrid_events_to_1s():
    """Eventos irregulares -> malla 1 s: toma el último estado de cada segundo."""
    base = RAW.iloc[:200].copy()
    ev = pd.concat([base.assign(timestamp=base.timestamp + pd.Timedelta("0.2s")),
                    base.assign(timestamp=base.timestamp + pd.Timedelta("0.7s"))]).sort_values("timestamp")
    ev = ev.reset_index(drop=True)
    ev.loc[::2, "bid_px_1"] -= 0.05          # el estado "viejo" del segundo debe descartarse
    g = C.to_1s_grid(ev)
    assert len(g) == 200 and (g["timestamp"].diff().dropna() == pd.Timedelta("1s")).all()
    assert np.allclose(g["bid_px_1"], base["bid_px_1"].to_numpy())


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn(); print("OK  ", name)
    print("Todas las pruebas pasaron.")
