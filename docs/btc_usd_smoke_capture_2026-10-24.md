# NAVIER — decisión de instrumento y captura de humo BTC/USD

Fecha: 2026-10-24 (UTC).

## Decisión

Se registra BTC/USD, Kraken Spot, Spot WebSocket API v2, canal público L2 book, profundidad 10 como instrumento de la validación prospectiva alineada con NAVIER_V3_PROTOCOL.md. El protocolo congelado queda sin cambios. Esta corrida sólo verifica instrumentación, integridad temporal y persistencia; no evalúa features, retornos ni rentabilidad, y no es una sesión confirmatoria.

## Captura de humo

- Duración máxima de stream: 110 s (menor que el límite autorizado de 120 s), timeout externo del proceso: 125 s.
- Salida única: data/v3_prospective/smoke_btc_usd_20261024T170800Z/.
- Destino inspeccionado como inexistente antes de crear esta carpeta. Sin --overwrite. No se usa el orquestador multi-sesión ni las rutas históricas.
- Conexión de sólo lectura a wss://ws.kraken.com/v2, suscripción channel=book, symbol=BTC/USD, depth=10, snapshot=true.
- Código de salida, stdout y stderr se guardan por separado en la carpeta. Timeout o fallo deben dejar estado no exitoso y cualquier partial aislado.

## Resultado

Pendiente de completar tras la ejecución. Una prueba exitosa valida exclusivamente la instrumentación de esta captura corta, no continuidad prolongada ni ausencia demostrada de pérdidas (Kraken Spot WS v2 no expone sequence ID en el schema book).

Primera invocación (17:08:53 UTC): el driver alcanzó el timeout externo de 125 s (exit 124), sin stdout, sin Parquet y sin partial. Dos probes offline de event loop (Proactor y Selector) quedaron bloqueados antes de cualquier red; por ello no se atribuye el fallo al venue. Evidencia preservada en data/v3_prospective/smoke_btc_usd_20261024T170800Z/. No se intentará una nueva captura en sandbox.


## Resultado de la captura de humo (24-10-2026)

**Estado: PASS_SMOKE_ONLY** para adquisición breve y persistencia; no confirma modelo, continuidad prolongada ni ausencia de pérdidas.

- Instrumento real confirmado en suscripción y filas: BTC/USD, Kraken Spot WS v2, canal book, depth 10, endpoint wss://ws.kraken.com/v2. Sin autenticación ni trading.
- Captura efectiva: 110.375 s, dentro del máximo de 120 s. Stream solicitado: 110 s. Driver externo: 111.375 s, límite 125 s. Inicio 17:17:33.435777 UTC; fin 17:19:23.823223 UTC.
- Parquet: 3 884 filas (1 snapshot + 3 883 updates); capture_row_id consecutivo 0–3883; todos los símbolos BTC/USD, timestamps UTC no nulos, monotonic clocks no decrecientes, processing >= receipt, orden exchange no decreciente y libro no cruzado.
- Contadores: 3 995 mensajes; 111 ignorados; CRC failures 0; malformed 0; subscription errors 0; connection errors 0; reconnects 0; ties exchange 278; regressions 0; estado final VALID.
- Gaps medidos sobre diferencias entre exchange timestamps: 0 intervalos >3 s; máximo 2.76028 s. Esto no es una auditoría del bin 1s porque no se ejecutó resampleo.
- Latencia receipt→processing no se declara estimada: en este host monotonic usa GetTickCount64 con resolución 15.625 ms; 3 862/3 884 diferencias observadas son 0 ms, p50/p90/p95/p99 = 0 ms y máximo = 16 ms. El reloj de pared produce números más granulares pero no prueba offset/sincronización. No calcular ni usar estos percentiles como latencia real. Tampoco hay feature-ready timestamp.
- Verificación automatizada del Parquet y el manifiesto: 16/16 checks verdaderos en post_capture_validation.json. El hash SHA-256 en el manifiesto, el driver y lectura local coincide.

### Artefactos de la ejecución efectiva

Directorio único: data/v3_prospective/smoke_btc_usd_20261024T171200Z/

- btc_usd_l2.parquet — SHA-256 b6123f33a464751fdceeca1a5f78887bc28f2d74e3ab4205cb94b6c1ddb80b76
- btc_usd_l2.parquet.manifest.json — SHA-256 618e5518e5808968c6f0fed02b74953ecbe0ef8d0c696385bea4c2a9a3fdcaec
- post_capture_validation.json — resumen de 16 invariantes, contadores, hashes y límites
- stdout.log / stderr.log / exit_code.txt — stdout 1 700 bytes, stderr vacío, exit code 0
- driver_metadata.json — command, tiempos, timeout y hash; run_capture_smoke.py conserva el comando reproducible.

El manifiesto tiene schema version 2. Hash del protocolo durante la ejecución: 0183b474253d5b6f50f25aba7e463a925a4ff5183da99a3648736dd93095114a (sin cambios). Hashes de scripts/adapter del run están en post_capture_validation.json.

### Intento previo sin artefactos de mercado

La ejecución sandbox en data/v3_prospective/smoke_btc_usd_20261024T170800Z/ terminó con timeout externo a 125.063 s, exit code 124, sin stdout, Parquet ni partial. Dos pruebas offline del event loop de Windows (Proactor y Selector) también agotaron 4 s antes de comenzar una coroutine; por ello ese intento no acredita ni rechaza conectividad a Kraken. Se conservó como INCOMPLETE y no se repitió sobre esa carpeta. La captura live efectiva posterior usó carpeta independiente y ejecución fuera del sandbox autorizada.

### Criterios y siguiente acción

Cumplidos: instrumento, canal público, duración <120 s, checksum de los mensajes persistidos, metadata estructural, identidad de filas, hash/reconciliación, ausencia de output parcial presentado como final y pruebas offline (69 passed, 1 warning conocido). Inconclusos: cuantificación de latencia efectiva/feature-ready, sincronización NTP, pérdida de mensajes indetectable sin sequence ID y fiabilidad durante sesiones prolongadas. No iniciar evaluación prospectiva de variables hasta resolver la medida de latencia con un reloj monotónico de alta resolución (p. ej. perf_counter_ns) y aprobar captura operativa separada, sin reusar este smoke como dataset confirmatorio.
