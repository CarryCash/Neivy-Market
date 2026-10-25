"""Contrato de datos: cualquier fuente (sintética o real) debe producir este esquema."""
from dataclasses import dataclass

N_LEVELS = 10

BID_PX = [f"bid_px_{k}" for k in range(1, N_LEVELS + 1)]
BID_QTY = [f"bid_qty_{k}" for k in range(1, N_LEVELS + 1)]
ASK_PX = [f"ask_px_{k}" for k in range(1, N_LEVELS + 1)]
ASK_QTY = [f"ask_qty_{k}" for k in range(1, N_LEVELS + 1)]
RAW_COLUMNS = ["timestamp"] + BID_PX + BID_QTY + ASK_PX + ASK_QTY


@dataclass(frozen=True)
class Config:
    """Parámetros del pipeline. Todos son ventanas FINITAS (en segundos = filas de 1 s)."""
    horizon: int = 10          # H: horizonte del retorno futuro (s)
    vel_window: int = 5        # ventana de la velocidad u (pendiente MCO del log-mid)
    imb_smooth: int = 3        # suavizado de I antes de derivar
    dI_lag: int = 5            # diferencia temporal de I suavizada
    vol_window: int = 60       # ventana de volatilidad realizada
    ofi_window: int = 5        # ventana de suma del OFI
    imb_lags: tuple = (2, 5, 8)  # rezagos de I (control "lineal temporal" del baseline B+)
    ret_windows: tuple = (1, 5, 30)  # momentum del baseline

    @property
    def max_window(self) -> int:
        """Historia máxima necesaria hacia atrás (filas)."""
        return max(self.vol_window, max(self.ret_windows), self.dI_lag + self.imb_smooth,
                   max(self.imb_lags) + 1, self.vel_window) + 2


DEFAULT_CONFIG = Config()

# Esquema de metadatos y trazabilidad del resampleo 001.9
STATE_OBSERVED = "OBSERVED"
STATE_CARRIED_FORWARD = "CARRIED_FORWARD"
STATE_GAP_DISCONTINUITY = "GAP_DISCONTINUITY"

RESAMPLE_META_COLUMNS = [
    "symbol",
    "updates_count",
    "state_source",
    "staleness_ms",
    "last_checksum",
    "capture_row_id",
    # Additive 001.10 availability metadata (null for legacy event files).
    "received_at",
    "received_monotonic_ns",
    "processed_at",
    "processed_monotonic_ns",
    "frame_received_monotonic_ns",
    "state_processed_monotonic_ns",
    "state_validated_monotonic_ns",
]

RESAMPLED_L2_COLUMNS = ["timestamp"] + RESAMPLE_META_COLUMNS + BID_PX + BID_QTY + ASK_PX + ASK_QTY

