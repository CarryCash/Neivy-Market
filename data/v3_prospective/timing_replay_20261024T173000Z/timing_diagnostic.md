# NAVIER V3 — diagnóstico temporal y disponibilidad de features

**Estado: `PARTIAL_TIMING_DIAGNOSTIC`**  
**Alcance:** replay offline de la captura de humo ya existente. No es una evaluación predictiva ni económica.

## Evidencia y reloj

El Parquet de entrada tenía 3.884 filas y su SHA-256 fue idéntico antes y después del replay (`b6123f33a464751fdceeca1a5f78887bc28f2d74e3ab4205cb94b6c1ddb80b76`). La captura conserva `timestamp` (evento exchange), `received_at` y `processed_at` (UTC local, ns en el esquema), y `received_monotonic_ns`/`processed_monotonic_ns` (nanosegundos monotónicos locales a la sesión). `capture_row_id` identifica el orden de captura.

En este host, `time.monotonic_ns()` usa `GetTickCount64()` con resolución declarada de 15,625 ms. De 3.884 duraciones recepción→procesamiento, 3.862 (99,43 %) resultan cero y el máximo es 16 ms. Es evidencia de cuantización insuficiente para medir la mayoría de las duraciones cortas, no evidencia de procesamiento instantáneo. Por eso se omiten percentiles de esas marcas.

`time.perf_counter_ns()` usa `QueryPerformanceCounter()`, resolución declarada de 100 ns. En 100.000 diferencias sucesivas de llamadas se observaron 30.707 ceros; el mínimo y mediana positivos fueron 100 ns. La medida tiene resolución efectiva sub-microsegundo para este replay, aunque el resultado es dependiente del host y no describe la precisión del timestamp de mercado.

No se restaron relojes entre sí. El timestamp del exchange y los UTC locales no permiten latencia exchange→recepción sin una verificación de sincronización; los contadores monotónicos sólo se comparan dentro del mismo dominio/reloj.

## Replay causal

El Parquet contiene estados L2 completos que el adaptador ya validó con CRC, no el payload WebSocket delta original. Por tanto, no se repitió la reconstrucción delta ni la validación CRC: esos datos no están almacenados. Se ejecutó el resampleador existente respetando el orden de captura; 109 intervalos de 1 s resultaron: 107 `OBSERVED` y 2 `CARRIED_FORWARD`. Para cada estado seleccionado se verificó que el timestamp del evento fuente no fuese posterior al cierre de su intervalo.

Se ejecutó el `compute_features` V3 existente con `with_target=False`; no se calcularon labels ni se alteró ninguna definición o parámetro V3. Las siete columnas V3 quedaron completas en 50/109 filas; el calentamiento de la ventana de 60 s explica que esta captura corta no pueda producir todas las filas válidas. Se vincularon las filas al `capture_row_id` del estado de libro seleccionado. La causalidad de cálculo usa solamente filas de libro actuales y previas; el chequeo de límites temporales del replay y las pruebas existentes de causalidad/feature pipeline respaldan esta propiedad.

El consumidor actual es por lotes, no un evaluador online. `feature_ready_replay_elapsed_ns` en `feature_availability_replay.csv` marca el retorno del lote completo en el replay; **no** representa el instante en que cada feature habría estado disponible en captura ni permite medir captura→feature-ready.

## Coste de replay medido

Medido con `perf_counter_ns`; cada etapa tuvo una sola observación, por lo que sólo se informa el tiempo de esa ejecución y se omiten percentiles:

| Etapa | Tiempo |
|---|---:|
| Lectura Parquet | 86,37 ms |
| Validación de entrada | 10,36 ms |
| Resampleo/selección causal de estados | 32,21 ms |
| Cálculo batch de features V3 | 23,05 ms |
| Total desde inicio de lectura a fin de features | 151,99 ms |

Estos valores describen una reproducción offline de 3.884 eventos en este equipo. No son latencia de producción ni de ejecución en exchange.

## Pruebas y archivos

Pruebas dirigidas: `tests/test_replay_v3_timing.py`, `tests/test_resampler_001_9.py` y `tests/test_features_v3.py`: **20 passed**. Suite completa: **72 passed**, con una advertencia preexistente de división por cero en `tests/test_robustness_001_6.py::test_constant_price_numerical_stress` (`navier_lab/features.py:126`).

Artefactos de salida: `timing_report.json`, `resampled_l2_1s.parquet`, `features_v3.parquet`, `feature_availability_replay.csv`. El script reproducible es `scripts/replay_v3_timing.py`. La captura fuente y el protocolo V3 no se modificaron.

La carpeta de replay anterior `timing_replay_20261024T172000Z` se conserva íntegra como primer ensayo exploratorio; sus percentiles no deben utilizarse. La medición final es la de esta carpeta, donde se omiten percentiles para etapas con una sola muestra y para marcas capturadas con resolución insuficiente.

## Limitaciones y decisión

- No hay reloj monotónico de alta resolución común entre recepción y cálculo de features para esa captura histórica.
- El pipeline calcula features en batch; falta un camino online que pueda marcar `feature_ready` al publicar cada fila.
- No se guardaron frames WebSocket crudos; el replay no verifica de nuevo la reconstrucción delta ni CRC.
- El canal Kraken no aportó secuencia numérica en este artefacto; CRC y contadores no descartan todas las pérdidas silenciosas.
- Una captura de humo de 110 s no cumple el tamaño ni diseño del bloque prospectivo V3, y no permite inferir capacidad predictiva o rentabilidad.

**Decisión:** la causalidad histórica de resampleo/features se pudo comprobar offline, pero la disponibilidad temporal real no se pudo medir fielmente. No iniciar todavía la evaluación prospectiva; primero instrumentar captura y publicación online con el mismo `perf_counter_ns` dentro del proceso, persistir timestamps de recepción/validación/feature-ready y validar integridad en una nueva captura aislada. Luego cumplir el tamaño y congelación de validación del protocolo.
