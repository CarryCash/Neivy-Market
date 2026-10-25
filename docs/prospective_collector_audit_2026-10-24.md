# NAVIER — auditoría del recolector y preparación prospectiva

**Fecha:** 24 de octubre de 2026  
**Alcance:** auditoría del recolector real de Kraken Spot L2, persistencia, resampleo y orquestación V3; cambios mínimos de observabilidad temporal y prevención de sobrescritura. No se realizó captura live ni se modificó el protocolo V3 congelado, sus ecuaciones o variables.

## Diagnóstico ejecutivo

El proyecto sí tiene un adaptador implementado para Kraken Spot WebSocket v2. Este adapta snapshots y deltas, valida el CRC32 de top 10 y no emite una fila de libro que no supere el checksum. No usa números de secuencia porque el canal Spot WS v2 documentado no presenta un campo de secuencia. Al fallar, invalida el estado. La evidencia técnica de las siete sesiones archivadas reporta 0 errores CRC, 23 reconexiones totales y 7/7 estados finales válidos; ello no prueba por sí solo captura sin pérdida ni disponibilidad operativa sostenida.

No se consideró fiable para validar disponibilidad real de features sin ajustes: antes de este trabajo solo persistía timestamp del exchange y received_at UTC generado dentro de process_message; no guardaba reloj monotónico ni tiempo de estado validado. Además, el resampler ordenaba eventos por exchange timestamp, lo cual podía reordenar transiciones si el timestamp retrocedía. Estos huecos se corrigieron de forma aditiva. La capacidad de datos reales no fue puesta a prueba en esta ejecución porque no se hizo conexión live.

**Bloqueo de protocolo:** el manifiesto de captura independiente y la configuración V3 congelada identifican BTC/USD; el pedido actual especifica BTC/USDT. El adaptador acepta ambos y su default es BTC/USDT, pero una futura sesión BTC/USDT no es el mismo instrumento que las capturas V3 archivadas ni puede llamarse validación confirmatoria de ese protocolo sin registrar formalmente la desviación. NAVIER_V3_PROTOCOL.md se mantuvo intacto.

## 1. Archivos y funciones relevantes

| Ruta | Función / responsabilidad |
|---|---|
| navier_lab/collector.py | Fuentes de datos; KrakenL2Source sigue siendo un stub deliberado. No es el colector efectivo. |
| navier_lab/kraken_ws_v2.py | KrakenSpotBookV2Adapter.process_message mantiene libro, aplica cambios y CRC; stream maneja conexión, duración, reconexiones y salida de estados válidos. |
| scripts/capture_kraken_l2.py | CLI de captura; buffers de filas Parquet y manifiesto JSON con hashes y contadores. |
| navier_lab/resampler.py | resample_l2_to_1s asigna eventos a bins causales (T−1,T], forward-carry acotado y gap discontinuities. |
| navier_lab/schema.py | Contrato L2 a 10 niveles y esquema de salida 1s. |
| scripts/resample_l2_1s.py | Runner batch del resampler y manifiesto de auditoría. |
| scripts/run_v3_capture.py | Orquestador de captura, resampleo y controles de calidad por sesión. |
| NAVIER_V3_PROTOCOL.md, docs/NAVIER_001_8_KRAKEN_README.md, docs/NAVIER_001_9_RESAMPLER_README.md | Protocolo científico y documentación del feed/transformación. |
| tests/test_kraken_ws_v2_001_8.py, tests/test_collector_001_7.py, tests/test_resampler_001_9.py | Fixtures de checksum, reconstrucción genérica, secuencia interna y causalidad/resampleo. |

El reconstructor genérico orderbook_reconstrcutor.py no es la ruta de Kraken. Acepta sequence +1 bajo un contrato interno y sus pruebas no acreditan una secuencia de exchange.

## 2. Datos y timestamps

### Existencia verificada

La inspección de metadatos Arrow de la primera captura histórica encontró 183 933 filas y 92 row groups. El Parquet contiene:

- timestamp: timestamp[ns, UTC], timestamp de evento/libro del exchange, formato RFC3339.
- received_at: timestamp[ns, UTC], hora de pared local que el código anterior muestreaba al entrar a process_message. Es aproximación a recepción, no monotónica ni independiente de ajustes del reloj del host.
- checksum: CRC32 entero.
- symbol y niveles bid/ask 1–10 como double.

No contiene secuencia de exchange, timestamp monotónico, instante de libro validado/procesado, ID persistente de fila, payload bruto ni detalle de desconexiones.

### Esquema aditivo de captura 001.10

Las filas nuevas registran:

- timestamp: evento de exchange, UTC.
- capture_row_id: secuencia local única, 0-based, asignada al persistir filas válidas; no es secuencia del exchange.
- received_at y received_monotonic_ns: reloj UTC y monotónico tomados inmediatamente al recibir el frame del WebSocket; el monotónico solo es comparable dentro de la misma ejecución/sesión.
- processed_at y processed_monotonic_ns: reloj UTC y monotónico al terminar parseo, actualización del libro y validación CRC.
- Parquet schema metadata y manifiesto indican capture_schema_version=2; las columnas previas se conservan.

processed_at es disponibilidad de estado validado, no finalización del cálculo V3 ni momento en que una orden hipotética podría llegar al mercado. La salida 1s propaga tiempos de disponibilidad de la última actualización que contribuye al estado elegido; valores null en archivos legacy significan que esos tiempos no se midieron.

## 3. Integridad L2, reconstrucción y orden

- La guía oficial de Kraken indica que cada snapshot/update de book contiene checksum CRC32 de top 10, que pueden existir varias mutaciones al mismo nivel en un mensaje y que los updates se procesen en secuencia. El esquema book Spot WS v2 consultado no expone campo seq. El adaptador aplica todas las mutaciones, elimina qty=0, recorta profundidad y compara CRC antes de persistir.
- Al checksum incorrecto, mensaje malformado o desconexión, invalida y deja de producir estados hasta un snapshot. La ruta stream ahora reconecta inmediatamente al invalidarse por checksum, timestamp fuera de orden u otro estado que exige resincronización.
- El adaptador nuevo admite timestamps de exchange iguales (los cuenta), exige RFC3339 con zona y rechaza regresiones; se invalida para reconectar. El resampler conserva el orden original estable de recepción y rechaza regresiones en vez de ordenar estados fuera de secuencia.
- CRC por estado es una comprobación fuerte de coherencia del top 10, pero no sustituye un sequence ID. No se puede localizar exactamente el mensaje perdido ni distinguir/contar duplicados de frames con certeza en los archivos históricos. Los nuevos contadores separan empates y regresiones de timestamps; no inventan IDs de secuencia.
- Cada fila persistida es un estado completo L2 validado después de un mensaje. Permite volver a calcular features V3 basadas en la secuencia temporal de estados almacenados. No permite volver a ejecutar el parser/delta feed original ni auditar las mutaciones individuales; los frames y deltas crudos no se guardan.
- La binning causal usa (T−1s,T] y el estado más reciente por timestamp en el bin. En empate, la posición recibida decide. Ahora cualquier regresión hace fallar el resampleo, no se corrige silenciosamente con sort.

## 4. Fallos demostrados y riesgos

### Fallos de diseño demostrados por código

1. No existían receive_monotonic ni processing/validation timestamps.
2. El resampler ordenaba por timestamp de exchange y ocultaba posibles regresiones del stream.
3. El CLI eliminaba primero el output y manifiesto existentes al usar --overwrite y escribía directamente al archivo final; un fallo podría dejar un artefacto parcial en esa ruta.
4. run_v3_capture.py apuntaba por defecto a data/v3_validation/sessions, reutilizaba IDs v3_val_session y pasaba --overwrite, y escribía docs/v3_capture_manifest.md. Una reutilización podía reemplazar archivos históricos.
5. El campo existente received_at se muestreaba en process_message, después del read de WebSocket y sin reloj monotónico.
6. El stream incrementa contador de reconnects y vuelve a suscribirse con snapshot, pero oculta detalles de excepciones de transporte y no persiste duración/causa por desconexión.
7. La documentación de collector.py afirma que el adaptador real aún no está implementado; quedó desactualizada frente a kraken_ws_v2.py.

### Riesgos que quedan sin demostrar o resolver

- No se hizo captura live ni prueba prolongada; no se puede afirmar que la red, host y exchange producirán continuidad suficiente.
- No se midieron sincronización NTP/offset del reloj local, latencia de recepción, retraso de cola, pérdida de escritura ni saturación del proceso.
- No se guardan mensajes crudos, ping/pong, causa/código de cierre, ni secuencia de exchange.
- El guardado Parquet es por lotes; la nueva versión protege el output final con archivo temporal y replace al completar. Una ejecución interrumpida retiene el parcial con nombre único, no es dato final.
- No hay registro del instante en que las variables V3 terminan de calcularse ni latencia desde feature-ready hasta decisión.
- Un CRC de top 10 no valida niveles fuera de esos diez, aun cuando profundidad mayor se solicite.
- Las capturas V3 archivadas tienen 23 reconexiones (incluidas 16 en sesión 3); no hubo CRC failures según el manifiesto. Esa experiencia evidencia discontinuidades, no captura continua.

## 5. Pruebas existentes y ejecutadas

Pruebas existentes revisadas:

- Kraken: mensaje de suscripción pública, fixture oficial CRC, snapshot/update/delete, rechazo de checksum y símbolo no suscrito.
- Reconstrucción genérica: snapshot, deltas, sequence gap, libro cruzado, resampleo incremental y reversión.
- Resampler 001.9: frontera causal, empate determinista, estados de gap y compatibilidad de features.

Pruebas añadidas: timestamps de recepción/procesamiento y monotónico, regresión exchange (invalida hasta nuevo snapshot), empate permitido, rechazo de regresión por el resampler y propagación de disponibilidad por bin.

Ejecutado: python -m pytest -q -p no:cacheprovider tests. Resultado: 67 passed, 1 warning esperado en test_constant_price_numerical_stress (división por cero en Re_m con precio constante; la prueba contempla el infinito). Tests enfocados Kraken/resampler/reconstructor: 23 passed. websockets instalado en el entorno: 15.0.1. No se ejecutó captura de red, resampleo de capturas históricas, ni órdenes.

## 6. Cambios mínimos hechos

- navier_lab/collector.py
- navier_lab/kraken_ws_v2.py: inyección del instante de recepción desde el loop WebSocket, timestamps monotónicos, instante de estado validado, contador de empates/regresiones y rechazo/reconexión ante regresión.
- navier_lab/schema.py y navier_lab/resampler.py: metadatos de disponibilidad aditivos y rechazo de timestamps de exchange no monótonos, preservando orden de llegada para empates.
- scripts/capture_kraken_l2.py: schema versionado 2; Parquet escrito a temporal único y promovido al nombre final sólo al completar con filas; errores/interrupción quedan como parcial; replace de manifiesto atómico; no elimina un archivo existente al inicio.
- scripts/run_v3_capture.py: salidas por ejecución con ID nuevo en data/v3_prospective, nombres v3_prospective_session, sin bandera overwrite, manifiesto dentro de la ejecución y default BTC/USDT explícito como diferente del protocolo V3 BTC/USD.

NAVIER_V3_PROTOCOL.md, las ecuaciones y variables V3, Parquets históricos y resultados no se modificaron. Los nombres nuevos protegen los outputs por defecto; si el operador usa una ruta personalizada, los runners rehúsan sobrescribir por defecto.

## 7. Plan de captura/validación y aceptación

1. Resolver antes de capturar si se desea BTC/USD conforme al protocolo congelado o BTC/USDT como instrumento distinto/versionado. No mezclar ambas muestras ni llamarlas replicación idéntica.
2. Ejecutar una captura de humo corta y manualmente inspeccionable en ruta única. Verificar manifest SUCCESS, schema version 2, hash de parquet, timestamps no nulos/UTC, capture_row_id único y monotonic_ns no decreciente en orden de fila, processed_monotonic_ns >= received_monotonic_ns, timestamps exchange no regresivos, CRC failure=0 y recuperación con snapshot tras cualquier invalidez.
3. Ejecutar captura operativa de varias sesiones separadas; observar counters, duración, gaps, reconnects, datos por segundo, skew local vs exchange y retraso receive→processed. Guardar y versionar métricas y hashes. Asegurar límites de pérdida/gap con criterios predefinidos antes de ver resultados predictivos.
4. Resamplear a 1 s sin overwrite; verificar causalidad (T−1,T], orden y desempate reproducible; conservar received/processed de la actualización elegida.
5. Recalcular features V3 offline sin target leakage y estimar feature availability lag: processed_at − feature_time, más histograma/percentiles por sesión. Confirmar que decisión a tiempo T usa sólo features ya disponibles a T; de otro modo, desplazar el instante de decisión o excluir la observación según preregistro.
6. Separar el nuevo conjunto de cualquier tuning. Hash congelado de protocolo, código, configuración y datos antes del periodo de evaluación.

Criterios mínimos verificables: ningún timestamp ausente/regresivo; ninguna sesión aceptada tras pérdida de sincronía sin snapshot validado; integridad de checksum sin fallos no recuperados; partial no pasa por captura completa; manifiesto+hash concuerdan; gaps dentro de umbral predefinido; disponibilidad de features medida y alineada causalmente; instrumento consistente con protocolo. Aún no se cumple aceptación live.

## 8. Brechas que impiden iniciar una evaluación prospectiva válida

- Resolver conflicto de instrumento BTC/USD congelado vs BTC/USDT solicitado.
- Hacer y aprobar captura live de humo; esta auditoría fue offline.
- Definir antes de abrir resultados umbrales operativos de recepción/latencia, gaps, sincronización y continuidad; el límite de gaps de 3 s es provisional.
- Verificar horas de host y latencia efectiva, e incorporar feature-ready latency si se pretende afirmar disponibilidad de la feature completa.
- Confirmar que la captura no tendrá fallos recuperables ocultos por el stream; el manifiesto actual registra contadores agregados pero no detalle de cada desconexión.
- Congelar protocolo y calendario de sesiones nuevas sin consultar resultados predictivos del período reservado.

## 9. Siguiente paso mínimo

Primero registrar la decisión de instrumento sin tocar el protocolo V3 congelado. Después correr una única captura de humo corta en una ruta prospectiva única y auditar su manifest, integridad, clock offsets y latencia. Si BTC/USDT queda elegido, declararlo como desviación/versionado antes de captura y no presentarlo como réplica literal de BTC/USD V3. La captura corta verifica mecanismo, no potencia ni capacidad predictiva.

**Estimación de ingeniería adicional:** ninguna para timestamp/integridad básica, ya implementada; 0.5–1 día para medición de sincronía, log detallado de reconexiones y chequeo feature-ready después del smoke test. Tiempo de calendario para sesiones depende de disponibilidad/estabilidad de mercado y potencia requerida.

## Referencia de protocolo del venue

La documentación oficial de Kraken Spot WebSocket v2 Book describe snapshot/update con timestamp RFC3339 y checksum CRC32, y dice que los updates se procesan secuencialmente; el schema documentado no trae seq. Véase [Kraken Spot WebSocket v2 Book](https://docs.kraken.com/exchange/api-reference/spot-websocket-v2/book) y [la guía de checksum](https://docs.kraken.com/exchange/guides/websockets/book-checksum-v2).

## Archivos tocados

- navier_lab/collector.py
- navier_lab/kraken_ws_v2.py
- navier_lab/schema.py
- navier_lab/resampler.py
- scripts/capture_kraken_l2.py
- scripts/run_v3_capture.py
- tests/test_capture_filesystem.py
- tests/test_kraken_ws_v2_001_8.py
- tests/test_resampler_001_9.py






