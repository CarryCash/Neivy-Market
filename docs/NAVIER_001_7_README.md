NAVIER 001.7 — reconstructor L2 y resampleo incremental
Esta rama de desarrollo se añade sin modificar el experimento V0.1. Incluye un reconstructor de estado de libro independiente de la red y un resampleador incremental a 1 segundo.
Alcance actual
- navier_lab/orderbook_reconstructor.py
  - OrderBookReconstructor: snapshot completo + deltas normalizados, cantidades cero para borrar, validación de secuencia, profundidad, orden y libro cruzado.
  - OneSecondResampler: conserva el segundo final incompleto entre chunks, elige el último estado completo por segundo y acarrea el último estado válido sobre segundos sin eventos.
- tests/test_collector_001_7.py: reconstrucción, eliminación, salto de secuencia, recuperación por snapshot, libro cruzado, reversión temporal y equivalencia de resampleo por chunks.
Contrato de secuencia: importante
El reconstructor solo entiende un contrato interno normalizado donde cada delta tiene un sequence entero exactamente igual a last_sequence + 1. No es todavía un adaptador de Kraken ni Binance. Antes de conectar un exchange hay que implementar y probar sus reglas documentadas de snapshot, buffer, puente de secuencias/rangos, checksum y reconexión.
Seguridad de datos
El resampleador solo debe recibir estados completos y validados. Ante una desconexión o desincronización, el llamador debe detener la alimentación y llamar reset() antes de comenzar un nuevo segmento validado. No se debe rellenar hacia delante a través de un intervalo conocido como inválido.
Ejecutar pruebas
Desde la raíz del proyecto, en un entorno con pytest y pandas:
pytest tests/test_collector_001_7.py -q
pytest -q
El test de resampleo compara la salida concatenada de múltiples tamaños de chunk contra una referencia por lotes; esto verifica equivalencia de valores y timestamps, no identidad byte a byte de archivos Parquet.
Pendiente antes de datos reales
1. Elegir exchange y documentar su protocolo exacto.
2. Implementar adaptador de WebSocket + snapshot HTTP con secuencia/checksum del venue.
3. Añadir pruebas con fixtures oficiales/reales anonimizados y escenarios de reconexión.
4. Añadir escritor Parquet atómico y manifest.json con configuración, rango UTC, versión de código, hash de datos y hash del snapshot inicial.
5. Ejecutar prueba de larga duración y medir memoria, latencia y pérdida de mensajes.