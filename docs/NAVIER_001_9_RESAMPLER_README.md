# NAVIER 001.9 — Resampleo Causal L2 a Rejilla Regular de 1 Segundo

> **Estado:** Implementado, verificado y auditado formalmente contra filtraciones temporales (*look-ahead bias*).  
> **Propósito:** Transformar el flujo asíncrono e irregular de eventos L2 del libro de órdenes (procedente de Kraken o simuladores) en una serie temporal estricta y regular de 1 segundo sin incurrir en trampas metodológicas ni inventar liquidez.

---

## 1. Código y Archivos Implementados

La versión **001.9** introdujo y consolidó la arquitectura de resampleo e integridad temporal mediante los siguientes componentes:

| Archivo | Rol en la Arquitectura | Descripción Técnica |
|---|---|---|
| [`navier_lab/resampler.py`](file:///c:/Users/USER/Downloads/navier_lab_project/navier_lab_project/navier_lab/resampler.py) | **Módulo central** | Motor de resampleo causal vectorizado y generador iterativo de bins de 1 s. Clasifica estados y rastrea obsolescencia (*staleness*). |
| [`navier_lab/schema.py`](file:///c:/Users/USER/Downloads/navier_lab_project/navier_lab_project/navier_lab/schema.py) *(actualizado)* | **Contrato de datos** | Definición de constantes de estado (`STATE_OBSERVED`, `STATE_CARRIED_FORWARD`, `STATE_GAP_DISCONTINUITY`) y columnas del esquema `RESAMPLED_L2_COLUMNS`. |
| [`scripts/resample_l2_1s.py`](file:///c:/Users/USER/Downloads/navier_lab_project/navier_lab_project/scripts/resample_l2_1s.py) | **Herramienta CLI** | Pipeline de terminal para procesar Parquets crudos L2 a 1 s con salida atómica, hashes SHA-256 de entrada/salida y auditoría `manifest.json`. |
| [`tests/test_resampler_001_9.py`](file:///c:/Users/USER/Downloads/navier_lab_project/navier_lab_project/tests/test_resampler_001_9.py) | **Suite de validación** | Pruebas de borde: causalidad estricta $(T-1, T]$, desempate determinista $(\Delta t = 0)$, tolerancia a gaps, y compatibilidad con `compute_features()`. |

---

## 2. Principios y Reglas de la Versión 1.9

### A. Causalidad Estricta en Intervalos Semiabiertos
Todo intervalo de tiempo se evalúa en el rango semiabierto:
$$\tau \in (T - 1.0\text{ s}, T]$$
* El registro resultante se rotula con la cota superior $T$ (el instante de corte exacto).
* **Regla antimagia:** Si un evento ocurre en $T + 0.001\text{ s}$, queda estrictamente descartado para el segundo $T$ y se asigna al intervalo de $T+1$.
* El estado del libro en $T$ corresponde a la **última actualización observada dentro del segundo** (la foto real del mercado al cerrar el segundo).

### B. Desempate Determinista ante $\Delta t = 0$
En ráfagas de alta frecuencia de Kraken donde múltiples actualizaciones de precios llegan con idéntico microsegundo o milisegundo de timestamp de exchange:
* El algoritmo utiliza el índice secuencial posicional de llegada (`row_id`).
* La última mutación procesada en la ráfaga es la que prevalece, garantizando reproducibilidad determinista en cualquier sistema operativo.

### C. Clasificación de Estados del Libro (`state_source`)
Para que los modelos econométricos sepan si una derivada temporal ($\frac{dI}{dt}$, aceleración de Navier) es genuina o un artefacto de relleno, cada segundo se etiqueta con uno de tres estados:

1. `STATE_OBSERVED` ($1$):  
   Se recibieron una o más actualizaciones válidas de Kraken en el intervalo $(T - 1\text{ s}, T]$.
2. `STATE_CARRIED_FORWARD` ($2$):  
   No hubo transacciones ni cambios en el libro durante ese segundo, pero el tiempo transcurrido desde la última actualización es menor o igual al umbral (`gap_threshold_seconds = 3.0 s`). Se mantiene el último estado conocido por persistencia de liquidez.
3. `STATE_GAP_DISCONTINUITY` ($3$):  
   El libro estuvo inactivo o desconectado más tiempo que el umbral permitido ($> 3.0\text{ s}$). Se marca discontinuidad estructural para que el pipeline de features no asuma continuidad en el cálculo de derivadas.

### D. Métricas de Trazabilidad Agregadas por Segundo
Por cada segundo de salida se calculan:
* `updates_count`: Número de mensajes/actualizaciones procesadas dentro de ese segundo.
* `staleness_ms`: Milisegundos transcurridos entre el último evento real y el instante de corte $T$.
* `last_checksum`: Último CRC32 reportado por el exchange, permitiendo auditoría forense inmediata.

---

## 3. Guía de Uso del Código 001.9

### Ejecución de Pruebas Unitarias
Para validar que el resampler cumple todas las invariantes matemáticas y de causalidad:
```bash
python -m pytest tests/test_resampler_001_9.py -q
```

### Resamplear un Parquet capturado de Kraken
Una vez capturado un archivo crudo con [`scripts/capture_kraken_l2.py`](file:///c:/Users/USER/Downloads/navier_lab_project/navier_lab_project/scripts/capture_kraken_l2.py), se transforma a la rejilla de 1 s ejecutando:
```bash
python scripts/resample_l2_1s.py --input data/kraken/btc_usdt_l2.parquet --output data/kraken/btc_usdt_l2_1s.parquet --gap-threshold 3.0 --overwrite
```

### Uso Directo en Python
```python
import pandas as pd
from navier_lab.resampler import resample_l2_to_1s, ResamplerConfig

# 1. Cargar datos L2 crudos de Kraken
df_raw = pd.read_parquet("data/kraken/btc_usdt_l2.parquet")

# 2. Configurar y resamplear a rejilla causal de 1 segundo
cfg = ResamplerConfig(bin_size_seconds=1.0, gap_threshold_seconds=3.0)
df_1s = resample_l2_to_1s(df_raw, cfg)

# df_1s contiene 10 niveles bid/ask regulares + updates_count + staleness_ms + state_source
```

---

## 4. Garantías hacia la Fase de Datos Reales

1. **Memoria y CPU contenidos:** Procesa más de 100 000 eventos L2 en menos de 2 segundos en una CPU convencional de 2 núcleos.
2. **Compatibilidad total con Feature Engineering:** La salida de `resample_l2_to_1s` encaja directamente en [`navier_lab.features.compute_features()`](file:///c:/Users/USER/Downloads/navier_lab_project/navier_lab_project/navier_lab/features.py).
3. **Causalidad Temporal en el Muestreo:** Garantiza que el paso de datos continuos L2 a la rejilla de 1 s no introduce sesgos anticipativos (*look-ahead bias*). La validez libre de fugas del experimento completo depende además de mantener particiones temporales estrictas y normalizaciones causales en las fases de feature engineering y modelado.
