"""Suite de pruebas rigurosas para NAVIER 001.9: Resampleo causal L2 y validación científica."""
import numpy as np
import pandas as pd
import pytest

from navier_lab.resampler import resample_l2_to_1s, ResamplerConfig
from navier_lab.schema import (
    BID_PX, BID_QTY, ASK_PX, ASK_QTY,
    STATE_OBSERVED, STATE_CARRIED_FORWARD, STATE_GAP_DISCONTINUITY,
    Config,
)
from navier_lab.features import compute_features, NAVIER, NAVIER_V02


def _make_dummy_l2_event(ts: pd.Timestamp, mid: float = 100000.0, spread: float = 1.0) -> dict:
    row = {
        "timestamp": ts,
        "symbol": "BTC/USDT",
        "checksum": 12345678,
    }
    for i in range(10):
        row[f"bid_px_{i+1}"] = mid - spread / 2.0 - i * 0.5
        row[f"bid_qty_{i+1}"] = 1.0 + i * 0.1
        row[f"ask_px_{i+1}"] = mid + spread / 2.0 + i * 0.5
        row[f"ask_qty_{i+1}"] = 1.0 + i * 0.1
    return row


def test_strict_causality_and_bounds():
    """Verifica que ningún evento con tau > T afecte al segundo T (intervalo semiabierto (T-1, T])."""
    base = pd.Timestamp("2026-10-19 14:00:00.000", tz="UTC")
    # Dos eventos en (14:00:00, 14:00:01]
    e1 = _make_dummy_l2_event(base + pd.Timedelta(milliseconds=200), mid=100.0)
    e2 = _make_dummy_l2_event(base + pd.Timedelta(milliseconds=900), mid=105.0)  # Debería ser elegido para T=01
    # Un evento justo en 14:00:01.001 (pertenece al segundo T=02)
    e3 = _make_dummy_l2_event(base + pd.Timedelta(milliseconds=1001), mid=110.0)

    df = pd.DataFrame([e1, e2, e3])
    out = resample_l2_to_1s(df, ResamplerConfig(gap_threshold_seconds=3.0))

    assert len(out) >= 1
    # La primera fila debe ser 14:00:01
    row_1s = out.iloc[0]
    assert row_1s["timestamp"] == base + pd.Timedelta(seconds=1)
    # Debe tener el mid derivado de e2 (mid=105), NO de e3 (mid=110)
    assert row_1s["bid_px_1"] == 105.0 - 0.5
    assert row_1s["updates_count"] == 2
    assert row_1s["state_source"] == STATE_OBSERVED


def test_deterministic_tie_breaking_for_zero_diff_timestamps():
    """Verifica que ráfagas con idéntico timestamp seleccionen la última actualización procesada."""
    base = pd.Timestamp("2026-10-19 14:00:00.500", tz="UTC")
    # Dos actualizaciones con EXACTAMENTE el mismo timestamp pero orden secuencial diferente
    e1 = _make_dummy_l2_event(base, mid=100.0)
    e2 = _make_dummy_l2_event(base, mid=200.0)  # La segunda mutación en la ráfaga

    df = pd.DataFrame([e1, e2])
    out = resample_l2_to_1s(df)

    assert len(out) == 1
    row_1s = out.iloc[0]
    assert row_1s["bid_px_1"] == 200.0 - 0.5  # Selecciona unívocamente la última
    assert row_1s["updates_count"] == 2


def test_exchange_timestamp_reversal_is_rejected_instead_of_sorted():
    base = pd.Timestamp("2026-10-19 14:00:00.000", tz="UTC")
    first = _make_dummy_l2_event(base + pd.Timedelta(milliseconds=800), mid=100.0)
    second = _make_dummy_l2_event(base + pd.Timedelta(milliseconds=200), mid=101.0)
    with pytest.raises(ValueError, match="timestamp de exchange retrocede"):
        resample_l2_to_1s(pd.DataFrame([first, second]))


def test_resampler_propagates_availability_of_selected_book_state():
    base = pd.Timestamp("2026-10-19 14:00:00.000", tz="UTC")
    first = _make_dummy_l2_event(base + pd.Timedelta(milliseconds=200), mid=100.0)
    first.update({"capture_row_id": 4, "received_at": base + pd.Timedelta(milliseconds=220),
                  "received_monotonic_ns": 200, "processed_at": base + pd.Timedelta(milliseconds=225),
                  "processed_monotonic_ns": 225})
    second = _make_dummy_l2_event(base + pd.Timedelta(milliseconds=800), mid=101.0)
    second.update({"capture_row_id": 5, "received_at": base + pd.Timedelta(milliseconds=850),
                   "received_monotonic_ns": 800, "processed_at": base + pd.Timedelta(milliseconds=860),
                   "processed_monotonic_ns": 860})
    out = resample_l2_to_1s(pd.DataFrame([first, second]))
    assert out.loc[0, "received_at"] == second["received_at"]
    assert out.loc[0, "capture_row_id"] == 5
    assert out.loc[0, "received_monotonic_ns"] == 800
    assert out.loc[0, "processed_at"] == second["processed_at"]
    assert out.loc[0, "processed_monotonic_ns"] == 860


def test_gap_threshold_and_state_classification():
    """Valida la clasificación entre OBSERVED, CARRIED_FORWARD y GAP_DISCONTINUITY."""
    base = pd.Timestamp("2026-10-19 14:00:00.000", tz="UTC")
    # Evento en t=0.5s -> segundo T=1s (OBSERVED)
    # Silencio de 2 segundos -> segundo T=2s y T=3s (CARRIED_FORWARD)
    # Silencio excede umbral de 3.0s -> segundo T=4s y T=5s (GAP_DISCONTINUITY)
    e1 = _make_dummy_l2_event(base + pd.Timedelta(milliseconds=500), mid=100.0)
    e2 = _make_dummy_l2_event(base + pd.Timedelta(milliseconds=5500), mid=105.0)

    df = pd.DataFrame([e1, e2])
    cfg = ResamplerConfig(gap_threshold_seconds=3.0)
    out = resample_l2_to_1s(df, cfg)

    # Grilla de 1s a 6s (5.5s se redondea a cota de cierre T=6s)
    assert len(out) == 6
    # T=1s: OBSERVED
    assert out.iloc[0]["state_source"] == STATE_OBSERVED
    # T=2s: CARRIED_FORWARD (staleness = 1.5s <= 3.0s)
    assert out.iloc[1]["state_source"] == STATE_CARRIED_FORWARD
    assert out.iloc[1]["staleness_ms"] == pytest.approx(1500.0)
    # T=3s: CARRIED_FORWARD (staleness = 2.5s <= 3.0s)
    assert out.iloc[2]["state_source"] == STATE_CARRIED_FORWARD
    # T=4s: GAP_DISCONTINUITY (staleness = 3.5s > 3.0s)
    assert out.iloc[3]["state_source"] == STATE_GAP_DISCONTINUITY
    # Los niveles en GAP_DISCONTINUITY deben ser NaN para prevenir interpolación espuria
    assert np.isnan(out.iloc[3]["bid_px_1"])
    # T=6s: OBSERVED (recibe e2 en 5.5s)
    assert out.iloc[5]["state_source"] == STATE_OBSERVED


def test_v01_immutability_and_v02_coexistence():
    """Comprueba que NAVIER V0.1 conserva sus fórmulas y que V0.2 se calcula en columnas separadas."""
    # Generar 70 segundos continuos para que vol60 y target a 10s se calculen
    base = pd.Timestamp("2026-10-19 14:00:00.000", tz="UTC")
    rows = []
    for s in range(75):
        ts = base + pd.Timedelta(seconds=s)
        # Caminata aleatoria determinista en el mid
        mid = 100000.0 + s * 0.5 + (1.0 if s % 2 == 0 else -1.0)
        e = _make_dummy_l2_event(ts, mid=mid)
        e["state_source"] = STATE_OBSERVED
        e["staleness_ms"] = 50.0
        rows.append(e)

    df_1s = pd.DataFrame(rows)
    feats = compute_features(df_1s, Config(horizon=10, vol_window=60), with_target=True)

    # Verificar presencia de V0.1 intacto
    for col in NAVIER:
        assert col in feats.columns
    assert "re_m" in feats.columns
    assert "re_log" in feats.columns

    # Verificar presencia de V0.2 alternativa
    for col in NAVIER_V02:
        assert col in feats.columns
    assert "v02_l_vwap_bps" in feats.columns
    assert "v02_re_log_reg" in feats.columns

    # Verificar que tras calentamiento (>60 s) existan valores numéricos válidos en ambas
    valid_slice = feats.iloc[62:64]
    assert not valid_slice["re_log"].isna().any()
    assert not valid_slice["v02_re_log_reg"].isna().any()
    assert (valid_slice["v02_l_vwap_bps"] > 0).all()
