# NAVIER 001.8 — Kraken Spot WebSocket v2

## Incluye

- `navier_lab/kraken_ws_v2.py`: adaptador público para canal `book`, símbolo `BTC/USDT`, checksum CRC32 y recuperación mediante snapshot nuevo.
- `scripts/capture_kraken_l2.py`: captura estados válidos en Parquet por lotes, con manifiesto JSON y SHA-256.
- `tests/test_kraken_ws_v2_001_8.py`: pruebas sin conexión, incluyendo el ejemplo CRC32 oficial de Kraken.

## Protocolo importante

Kraken Spot WebSocket API v2 `book` no expone una secuencia monotónica `+1` por mensaje. Por eso este adaptador NO alimenta directamente el reconstructor genérico 001.7: mantiene su libro con reglas Kraken y valida cada estado mediante el checksum CRC32 del exchange. Procesa todos los cambios de un mensaje antes de verificar el checksum; `qty=0` elimina el nivel; recorta a la profundidad suscrita. Al fallar el checksum o desconectarse, invalida el libro y no emite datos hasta recibir un snapshot nuevo válido.

## Instalación

Desde la raíz `navier_lab_project`, con el venv activado:

```bash
python -m pip install websockets pandas pyarrow pytest
```

No requiere API key. Solo conecta a `wss://ws.kraken.com/v2` y suscribe el canal público `book`; no contiene funciones de envío de órdenes.

## Pruebas locales

```bash
python -m pytest tests/test_kraken_ws_v2_001_8.py -q
```

## Captura de 5 minutos

```bash
python scripts/capture_kraken_l2.py --symbol BTC/USDT --depth 10 --seconds 300 --output data/kraken/btc_usdt_l2.parquet
```

Si el archivo existe, el script se detiene para no sobrescribir datos; para permitirlo añade `--overwrite`. El manifiesto `.parquet.manifest.json` incluye los parámetros de captura, contadores, estado final y hash del archivo. Cada fila es un estado de libro tras un mensaje válido, no una vela ni una observación cada segundo.

## Límites de la versión

- No se han enviado órdenes ni se usan credenciales.
- No se ha verificado una sesión live desde este entorno; la primera ejecución debe ser corta y revisarse manualmente.
- Si Kraken rechaza `BTC/USDT`, el script no cambia de símbolo silenciosamente: verifica la disponibilidad del par en el exchange.
- Los precios/cantidades se validan en `Decimal`; se convierten a float al exportar filas Parquet.
- Esta captura de microestructura no demuestra ventaja predictiva ni rentabilidad.

## Fuentes oficiales

- Book (Level 2), Kraken Spot WebSocket v2: https://docs.kraken.com/api/docs/websocket-v2/book/
- Book checksum v2: https://docs.kraken.com/exchange/guides/websockets/book-checksum-v2
