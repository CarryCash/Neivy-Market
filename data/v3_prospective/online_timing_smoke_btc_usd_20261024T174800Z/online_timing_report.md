# NAVIER V3 — instrumentación online y smoke de disponibilidad

**Estado: `PASS_ONLINE_TIMING_SMOKE`**  
Este resultado valida la instrumentación y equivalencia temporal/numérica para una sesión corta. No valida capacidad predictiva, rentabilidad ni operación sostenida.

## Flujo instrumentado

Kraken Spot WebSocket v2 `book` (BTC/USD, profundidad 10) → recepción de frame → aplicación del update L2 → chequeo CRC → asignación de `capture_row_id` → cierre del intervalo causal de 1 s cuando llega un evento válido posterior → selección por el resampleador existente → `compute_features(..., with_target=False)` → entrega síncrona a la cola de features en el mismo proceso. El sidecar Parquet se persiste al terminar la sesión.

Las marcas `*_monotonic_ns` nuevas usan `time.perf_counter_ns()` / `QueryPerformanceCounter()` en el mismo proceso. UTC de pared queda para trazabilidad. No se restan timestamps de relojes distintos. La captura tiene `capture_row_id` del estado fuente y del frame disparador, además de los IDs de eventos en las ventanas de dependencia de cada feature.

## Captura e integridad

- Solicitud de captura: 120 s. Span entre primera y última recepción de frame: **117,409 s** medido con `perf_counter_ns`. El manifiesto indica **126,406 s** hasta terminar el procesamiento y la finalización del archivo; por tanto, la cola final de procesamiento excede el tiempo de entrada, aunque el span observado de recepción queda dentro del límite solicitado.
- 3.945 estados L2 válidos, `capture_row_id` consecutivo, timestamps de exchange monótonos, libro final válido.
- 1 snapshot, 3.944 updates, 0 fallos CRC, 0 mensajes malformados, 0 regresiones de exchange, 0 reconexiones y 0 errores de transporte/suscripción. Hubo 755 timestamps de exchange empatados, permitidos y conservados en orden de recepción.
- 98 intervalos de 1 s finalizados: 39 filas publicadas con todas las features V3 disponibles y 59 no publicadas por calentamiento/NaN; ninguna discontinuidad produjo una fila publicable.
- SHA-256 L2: `620eb78d643530b96593ad7a6b0c9823d4239b6ec8d69823401dddde86c5c8c0`. SHA-256 sidecar de features: `7b9f5844d4b815250ccd1a144313f7f06cc57b819c2f0fa550241876b39bb20e`.

## Reloj y duraciones

`perf_counter` declara 100 ns. En 100.000 diferencias de llamadas consecutivas se observaron 3.269 ceros; el mínimo y mediana positivos fueron 100 ns. Los ceros en llamadas consecutivas reflejan que algunas llamadas caen en la misma marca del contador; ninguna duración observada en los eventos de la captura fue cero.

| Etapa (misma base monotónica) | n | Mediana | p90 | p95 | p99 | Máximo |
|---|---:|---:|---:|---:|---:|---:|
| Recepción → estado candidato procesado | 3.945 | 0,0408 ms | 0,0687 ms | 0,1026 ms | 0,1268 ms | 0,2308 ms |
| Recepción → estado validado por CRC | 3.945 | 0,0794 ms | 0,1333 ms | 0,1652 ms | 0,1986 ms | 0,3409 ms |
| Frame disparador → inicio de selección causal | 39 | 0,7099 ms | 0,8506 ms | 0,9302 ms | 1,1670 ms | 1,1745 ms |
| Selección/resampleo causal | 39 | 56,2516 ms | 60,5732 ms | 61,8205 ms | 70,9849 ms | 74,0738 ms |
| Estado seleccionado → inicio de features | 39 | 0,5403 ms | 0,6049 ms | 0,6293 ms | 0,7950 ms | 0,8930 ms |
| Frame disparador → `feature_ready` | 39 | 76,4742 ms | 88,1581 ms | 96,8662 ms | 97,9436 ms | 98,5307 ms |
| Inicio de cálculo V3 → `feature_ready` | 39 | 19,0186 ms | 21,3064 ms | 37,5511 ms | 40,2620 ms | 40,8996 ms |

La selección vuelve a procesar el historial causal conservado por el publisher y es el componente más costoso de esta medición. El coste pertenece a este equipo y a esta implementación; el smoke no establece capacidad de carga o SLA.

## Equivalencia batch-online y causalidad

Se recalcularon resampleo y features con las funciones existentes, usando todo el Parquet. Las 39 filas publicadas coinciden por intervalo y estado fuente con el resultado batch. Máxima diferencia absoluta por columna:

| Feature V3 | Diferencia absoluta máxima |
|---|---:|
| `v03_pnpc_k3` | 0 |
| `v03_pnpc_k5` | 0 |
| `v03_liq_conc_ask` | 0 |
| `v03_liq_conc_bid` | 0 |
| `v03_impact_conc_k3` | 0 |
| `v03_depth_replenish_ask` | 4,44e-16 |
| `v03_depth_replenish_bid` | 2,22e-16 |

La tolerancia `rtol=1e-12`, `atol=1e-12` cubre únicamente ruido de punto flotante; las fórmulas se ejecutan por la misma función congelada. El validador comprobó que el estado fuente coincide con el resampleo batch, que el frame disparador llega después del cierre de su intervalo, que todos los IDs de dependencia existen y no son posteriores al intervalo, y que se respeta el orden recepción → validación → selección → cálculo → disponibilidad.

## Pruebas y limitaciones

Suite completa: **75 passed**, 1 advertencia ya conocida en la prueba de estrés de precio constante (`features.py:126`, división por cero de `re_m`). Las pruebas nuevas cubren la equivalencia de la ruta, el orden de marcas, los IDs, el rechazo de filas no calentadas y el versionado del sidecar. El adaptador ya tiene pruebas para CRC inválido, actualización fuera de orden y necesidad de snapshot de recuperación; esta sesión real no experimentó esos eventos.

El protocolo V3 conserva SHA-256 `0183b474253d5b6f50f25aba7e463a925a4ff5183da99a3648736dd93095114a`; la captura histórica previa conserva SHA-256 `b6123f33a464751fdceeca1a5f78887bc28f2d74e3ab4205cb94b6c1ddb80b76`. No se evaluaron targets, modelos, señales ni costes de trading.

Limitaciones restantes: Kraken no aporta sequence ID, así que CRC/contadores no prueban ausencia de toda pérdida silenciosa; la smoke es una sola sesión de 120 s y no prueba operación sostenida; `feature_ready` es entrega a un consumidor síncrono en memoria y no latencia de un consumidor externo; la instrumentación no implica disponibilidad ni latencia de ejecución de órdenes. La primera captura de esta fase quedó preservada en su carpeta separada; esta carpeta contiene la sesión validada final.
