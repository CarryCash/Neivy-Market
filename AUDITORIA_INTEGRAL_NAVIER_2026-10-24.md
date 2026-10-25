# NAVIER — auditoría integral y diagnóstico de capacidad predictiva

**Fecha:** 24 de octubre de 2026  
**Alcance:** auditoría del proyecto entregado en `navier_lab_project_clean.zip`.  
**Resultado general:** NAVIER dispone de un pipeline de investigación real y resultados OOS reproducibles; no ha demostrado una mejora predictiva incremental robusta ni utilidad económica. La conclusión del experimento geométrico V3 es **inconclusa para el contraste OOS**, con estimación débil y negativa en el holdout reportado. Ese holdout está contaminado por solapamiento del target al entrenar y no debe tratarse como una prueba final válida.

## A. Estado actual del proyecto

El directorio de trabajo donde se solicitó la auditoría estaba vacío, sin archivos fuente ni commits. El proyecto está en el ZIP de 192 MB indicado por el usuario. El ZIP contiene 169 miembros: módulos, scripts, pruebas, dos notebooks, datos L2 reales y sintéticos, resultados, manifiestos e informes. Se leyó y analizó desde una copia temporal aislada en `_audit_copy`; los archivos funcionales del ZIP no se editaron. La copia de auditoría no es una versión nueva del proyecto.

La evolución que muestran los artefactos es:

1. **Notebook 001 / V0.1:** pipeline y experimentos con datos sintéticos controlados.
2. **Auditoría 001.5 y versiones 001.6–001.9:** pruebas técnicas, reconstrucción/captura de L2 de Kraken y resampleo causal a un segundo.
3. **Dataset V2:** 11 sesiones reales de BTC/USD y evaluación acumulativa; los JSON archivados registran resultados adversos para NAVIER.
4. **V3:** siete sesiones independientes reales de BTC/USD, un dataset congelado, un evaluador preespecificado y una evaluación de modelos geométricos. El resultado principal se reprodujo exactamente, pero el corte del holdout tiene contaminación temporal demostrable.

El registro indica que la línea geométrica estática no añadió una mejora confiable. No hay base para afirmar que NAVIER sea rentable. Esta conclusión es compatible con los resultados disponibles aunque el holdout V3 se invalide: el walk-forward no muestra significación tras FDR y las comparaciones frente a varias referencias convencionales son negativas.

## B. Flujo real de datos y ejecución

```mermaid
flowchart TD
    A[Kraken Spot WebSocket v2: libro L2, 10 niveles] --> B[Adaptador: snapshot + deltas + checksum CRC32]
    B --> C[Parquet de eventos: timestamp exchange, recepción, estado]
    C --> D[Resampler 001.9: intervalos (T-1s,T], observado/arrastrado/gap]
    D --> E[Features convencionales: spread, profundidad, imbalance, OFI, retornos, vol]
    D --> F[Features NAVIER: u, dI/dt, gradientes, curvaturas, Re y variantes V02/V03]
    E --> G[Target a 10 s: retorno mid nominal y normalizado]
    F --> G
    G --> H[Modelos lineales anidados B, B+, B++, B+++, E]
    H --> I[Walk-forward con normalización en train, purga/embargo]
    H --> J[Holdout cronológico reportado: corte con solapamiento del target]
    I --> K[MSE / ΔR², Diebold–Mariano HAC, FDR, bootstrap]
    J --> K
    K --> L[No hay simulación de ejecución ni PnL neto]
```

### Reconstrucción del flujo

1. **Datos recibidos.** El adaptador Kraken Spot WebSocket v2 recibe mensajes públicos `book`, mantiene un libro de 10 niveles, aplica deltas y verifica checksum CRC32. Las capturas guardan estados válidos en Parquet; el manifiesto registra contadores, estado final y SHA-256. Los siete archivos V3 corresponden a BTC/USD y reportan 1,054,779 mensajes raw, 16,750 bins de un segundo y cero fallos de checksum. La sesión 3 registra 16 reconexiones y la 2 registra 5; se requiere snapshot nuevo tras recuperación.
2. **Resampleo.** El resampler selecciona causalmente el último estado dentro de `(T−1s,T]`, conserva `updates_count`, fuente y antigüedad, y marca gaps. No interpreta cada bin arrastrado como actualización nueva.
3. **Variables.** Calcula spread y profundidad, imbalance completo y top-1, OFI sobre snapshots consecutivos, retornos de 1/5/30 s, volatilidad de 60 s, rezagos de imbalance y variables NAVIER. V0.1 usa pendiente de log-mid, cambio suavizado de imbalance, gradientes/curvaturas del tamaño por nivel y proxy `Re_m`. V02/V03 añaden alternativas separadas por prefijo.
4. **Objetivo.** Horizonte primario de 10 s. `y_bps = 10,000 × [log(mid(t+10s)) − log(mid(t))]`. El modelo usa también `y = y_bps / (vol60_bps × sqrt(10))`, con suelo de volatilidad de 0.01 bps y filtros de discontinuidad/obsolescencia. Es una etiqueta para predecir retorno, no una señal de trading ya ejecutable.
5. **Modelos.** Regresiones lineales ridge muy débil con features estandarizadas con estadísticas de entrenamiento. V3 compara controles convencionales crecientes (B, B+, B++, B+++) contra E, que añade tres features geométricas; H1a de reposición es exploratorio. No hay red neuronal, LLM ni ejecución de órdenes.
6. **Evaluación.** Walk-forward expansivo, 5 segmentos definidos por 4 cortes de test, purga y embargo de 10 filas a cada corte, MSE/ΔR² pareado, Diebold–Mariano HAC con lags 10/20/40, FDR Benjamini–Hochberg en cuatro contrastes confirmatorios y bootstrap estacionario de longitud media 15. También se reporta un holdout final del 20%, cuyo corte no purga las etiquetas de entrenamiento.
7. **Evidencia resultante.** Hay resultados sintéticos con señal plantada, evaluaciones reales V2/V3 y artefactos de calidad. Solo el experimento V3 se volvió a ejecutar aquí de forma independiente en la copia temporal; el resultado coincidió exactamente. Ningún resultado es un PnL neto.

## C. Componentes y estado

| Componente | Estado | Evidencia y límite principal |
|---|---|---|
| Notebook 001 y generador sintético | **Verificado** | Notebook ejecutado con outputs guardados; 100,000 filas por escenario. S2 tiene señal Navier plantada por diseño, así que detectarla valida comportamiento del pipeline sintético, no pronóstico de BTC. |
| Notebook y pruebas 001.5 | **Verificado con limitación** | Notebook tiene outputs guardados para 12,000 filas de `S2_navier`; afirma auditoría sintética, no de mercado. La suite actual ejecutada incluye las pruebas históricas. |
| Adaptador/capturador Kraken | **Verificado en el código y pruebas; operación live actual desconocida** | Implementa checksum y recuperación por snapshot; hay capturas reales y manifiestos. No se probó conexión nueva durante esta auditoría. La fuente genérica `KrakenL2Source` de V0.1 sigue siendo deliberadamente un stub; el camino real se añadió aparte en 001.8/V3. |
| Resampler 001.9 | **Verificado** | 48 pruebas pasan; reproducción sobre BTC/USDT real produjo los mismos 299 bins y el hash SHA-256 exacto guardado. |
| Features V0.1 y labels | **Verificado parcialmente** | Fórmulas y pruebas de causalidad están presentes; las features usan el pasado y el label mira 10 s al futuro. `Re_m` de V0.1 sigue divergiendo a infinito cuando `vol60=0`; una prueba pasa precisamente porque comprueba ese fallo conocido. |
| Datasets reales V2/V3 | **Verificados por hash, reconstrucción integral no ejecutada** | Los hashes V2/V3 coinciden con manifiestos. Se reprodujo el resample BTC/USDT, no todo el build de 7 sesiones V3 desde los mensajes raw. |
| Evaluador walk-forward V3 | **Verificado/reproducido, con limitaciones inferenciales** | Las métricas guardadas se reprodujeron exactamente sobre el dataset congelado. El holdout tiene filtración por solapamiento del target. HAC/bootstrap agrupan puntos tras eliminar filas y unir sesiones/folds como si fueran una secuencia regular. |
| Evaluación económica | **Incompleta** | No hay estrategia de entrada/salida, sizing, coste integral, slippage, fill/cola, latencia de decisión/ejecución, PnL neto ni distribución de pérdidas. |
| Dependencias/reproducibilidad de entorno | **Incompleto** | `requirements.txt` limita versiones por rangos, no congela un lockfile. El entorno de esta auditoría difiere del entorno archivado; `statsmodels` no está instalado localmente. La evaluación reproducida no lo necesita. |

## D. Pruebas ejecutadas y resultados observados

Todas las acciones de ejecución se hicieron en `_audit_copy`, copia aislada del ZIP. La copia ocupó 212,511,770 bytes. No se ejecutaron órdenes ni se conectó a un sistema de trading.

| Ejecución | Resultado |
|---|---|
| Inventario de ZIP con `zipfile` | 169 miembros; `testzip()` no encontró miembro corrupto. |
| `python -m pytest -q -p no:cacheprovider` | **48 passed, 0 failed, 0 skipped, 1 warning, 19.70 s.** Advertencia en `features.py`: división por cero en `Re_m` bajo precio/volatilidad constante. `test_constant_price_numerical_stress` espera y afirma `inf`; el test no demuestra estabilidad finita de esa variable. |
| `python scripts/resample_l2_1s.py --input data/kraken/btc_usdt_l2.parquet --output data/kraken/_audit_reproduced_1s.parquet` | 15,086 eventos de entrada; 299 bins; 100% observados; el input SHA-256 coincide con manifiesto y el output SHA-256 reproduce exactamente `0b2e99…07364`. |
| Re-evaluación en memoria de `evaluate_dataset_v3` con holdout 0.20, k=5, purge=10, embargo=10, seed=42 | **Coincidencia exacta** con el JSON guardado: 13,558 observaciones limpias, 8,637 observaciones walk-forward, todas las métricas C1–C4, intervalos, folds y resultados de holdout. No se escribieron resultados de evaluación. |
| Auditoría del corte del holdout por timestamps del Parquet | **Fallo confirmado en aislamiento del holdout:** última fila usada en train 17:57:41 UTC, cuya etiqueta usa datos hasta 17:57:51; primera fila test 17:57:42. Nueve segundos de información del período test entran en la etiqueta de entrenamiento. |

**Entorno local de auditoría:** Python 3.10.9, NumPy 2.2.6, pandas 2.3.2, PyArrow 23.0.1, SciPy 1.15.3. `statsmodels` no instalado. El metadata archivado del run V3 informa NumPy 2.2.6, pandas 2.3.3, SciPy 1.15.3; la auditoría 001.5 registra PyArrow 24.0.0 y statsmodels 0.15.0. La evaluación pudo reproducirse pese a las diferencias locales mencionadas.

**Metadatos de ejecución existentes:** `execution_metadata_error.json` registra un intento fallido anterior por no encontrar los 7 artefactos congelados; `execution_metadata.json` registra una ejecución posterior exitosa de 29.578 s, con hashes de código/dataset coincidentes. No se oculta el fallo inicial. La evaluación posterior se volvió a reproducir en esta auditoría.

## E. Evidencia disponible sobre capacidad predictiva

### Experimentos sintéticos — no son evidencia de mercado

Notebook 001 simula tres mundos fechados ficticiamente en 2000: S0 ruido, S1 señal convencional plantada y S2 señal de tipo Navier plantada. Sus resultados guardados reportan ausencia de señal NAVIER incremental en S0/S1 y señal detectada en S2. El resumen incluye 20 corridas Monte Carlo para S0 y 20 para S1, con cero veredictos positivos. Esto comprueba una propiedad del simulador y del proceso de evaluación bajo esos escenarios diseñados; no prueba que BTC contenga esa señal.

### Datos reales — evaluación V2

El manifiesto V2 contiene BTC/USD de Kraken, 11 sesiones acumuladas, 8,989 filas limpias y SHA-256 del dataset coincidente. Existen varios JSON de evaluación acumulativa (sesiones 1–2, 1–3, etc. hasta 1–11); todos reportan el veredicto histórico de fracaso/ausencia de evidencia incremental. Al reusar muestras acumuladas y cortes holdout entre iteraciones no son réplicas independientes ni una prueba confirmatoria final. No se reejecutaron aquí.

### Datos reales — evaluación V3 reproducida

El dataset V3 contiene 13,558 filas de 7 sesiones de BTC/USD Kraken. El manifiesto de captura dice 16,750 bins de 1 s, 988 bins de gap y 15,762 bins sin gap; el dataset final retiene 13,558 tras calentamiento y filtros adicionales de features, ventanas futuras y staleness. El manifiesto de captura también documenta que el protocolo había previsto 9 sesiones y se cerró con 7.

Contraste primario E frente a B+++:

| Métrica | Walk-forward | Holdout reportado* |
|---|---:|---:|
| ΔR² = 1 − MSE(E)/MSE(B+++) | +0.1922% | −0.5347% |
| Intervalo 95% bootstrap | [−0.6750%, +0.5024%] | No reportado |
| DM p nominal | 0.4771 | 0.5405 |
| p ajustado FDR | 0.7276 | No aplicado al holdout |
| Folds walk-forward con mejora | 3/4 | — |
| N | 8,637 | 2,712 |

`*`El holdout no es válido como prueba independiente por el solapamiento temporal documentado en D. Se conserva el resultado numérico, pero no se interpreta como estimación confirmatoria limpia.

E también empeora frente a B++, B+ y B en el walk-forward: ΔR² de −0.0736%, −0.1325% y −0.1392%, respectivamente. Sus intervalos bootstrap incluyen cero y los p-valores ajustados no son significativos. Por tanto, no existe evidencia demostrada de información geométrica incremental sobre las referencias convencionales. La magnitud puntual de +0.192% frente a B+++ es pequeña, incierta y desaparece frente a los controles más sencillos.

Las métricas guardadas muestran que la normalización `y_bps/(vol60×sqrt(10))` produce valores extremos: 45 filas con `|y|>10`, mínimo de `vol60` de 0.0104 bps en la muestra, y curtosis global muy alta. El análisis post-mortem atribuye esos extremos a una volatilidad denominadora casi nula, no a grandes movimientos de precio. La prueba de estrés en mercado constante también demuestra que la versión V0.1 de `Re_m` devuelve infinito.

## F. Brechas que impiden determinar valor científico/económico

1. **Holdout contaminado:** el evaluador usa todas las filas del 80% inicial para ajustar, sin purgar las últimas etiquetas que se extienden dentro del 20% reservado. Ya no puede presentarse ese período consultado como evaluación final intacta.
2. **Inferencia con discontinuidades:** las pérdidas de test de cuatro folds y siete sesiones se compactan en una matriz por fila. HAC aplica lags por fila y el bootstrap forma bloques que pueden cruzar límites de folds, huecos o sesiones. La dependencia existe: la autocorrelación guardada de `y_bps` en lag 1 es 0.93. Se debe respetar tiempo transcurrido y bloques/sesiones en la inferencia.
3. **Muestra limitada y pocas sesiones:** siete sesiones de unos 40 minutos, no nueve como estaba planificado. La cifra de 13,558 filas sobrestima la información independiente por autocorrelación; una auditoría guardada estima un tamaño efectivo aproximado de 1,478 bajo su método, que también debe justificarse.
4. **OFI de baja frecuencia:** `ofi_5` se calcula sobre snapshots resampleados a 1 s, no sobre cada mensaje L2 original. Puede perder cancelaciones/reordenamientos intrasegundo y no equivale sin más al OFI de eventos de alta frecuencia. La comparación es con OFI derivado de las mismas observaciones, no necesariamente con una referencia microestructural completa.
5. **Variables con fundamento operativo, no hidrodinámica demostrada:** gradientes, curvaturas y ratios son transformaciones del libro; el nombre físico no acredita una ley de flujo. La geometría estática V3 está muy correlacionada por rangos con ratios/OFI según el post-mortem archivado.
6. **Normalización inestable:** el suelo absoluto de `vol60` de 0.01 bps permite todavía valores enormes cerca del límite. El resultado depende del objetivo normalizado y de esta definición; debe reportarse también retorno nominal y sensibilidad preespecificada.
7. **Multiplicidad global:** FDR se aplica a los cuatro contrastes declarados en V3. No abarca retroactivamente las búsquedas exploratorias de horizontes, variables, escenarios sintéticos o las iteraciones V2. C5 está correctamente marcado exploratorio; la familia completa de investigación es mayor que cuatro tests.
8. **No hay predicción económica:** el modelo genera una media puntual del target, no intervalos/calibración de incertidumbre predictiva ni una política con umbral y posición. No hay evaluación de comisiones vigentes, spread de entrada/salida, slippage, fill, latencia de decisión/orden ni PnL neto/riesgo. Hay book y timestamps de recepción, pero esos registros no se convierten en simulación de ejecución.
9. **Reconstrucción end-to-end incompleta en esta auditoría:** hashes y metadatos validan artefactos; aquí se reprodujo el resample de 5 minutos y la evaluación V3. No se reconstruyeron los siete datasets de sesión y `research_dataset_v3.parquet` desde raw, así que la reproducibilidad end-to-end de esa etapa sigue sin demostrarse independientemente.
10. **Congelación de dependencias débil:** versiones admitidas por rangos y no un lockfile exacto; un miembro de requirements (statsmodels) falta en este entorno. La evaluación concreta no lo importa, pero otras investigaciones pueden variar.

## G. Próximo paso mínimo recomendado

### Hipótesis

Sobre BTC/USD L2 de Kraken, las features geométricas V03 reducen el MSE OOS del retorno normalizado a 10 s en al menos 0.10% frente al baseline B+++ que ya incluye features convencionales y el ratio OFI/profundidad. La alternativa nula es que no exista una mejora incremental reproducible. El retorno nominal a 10 s se reporta en paralelo para conservar magnitud interpretable.

### Experimento mínimo

1. Corregir el corte para que ninguna etiqueta de entrenamiento use precios posteriores al instante de origen del primer holdout; usar `label_end_time = timestamp + 10s` y purgar por tiempo, no solo por índice.
2. Antes de abrir nuevas etiquetas, versionar y congelar un addendum de protocolo, métrica, filtros, seeds, inferencia y regla de decisión. El holdout ya consultado no se reutiliza como prueba final; reservar nuevas sesiones posteriores, sin explorarlas para elegir features.
3. Ejecutar una comparación única E vs B+++ en filas idénticas, con walk-forward en sesiones anteriores y holdout cronológico posterior independiente. Calcular incertidumbre por bloques temporales continuos/sesión y reportar por sesión; mantener FDR para los contrastes adicionales que se preespecifiquen.
4. Reportar número de observaciones y sesiones, exclusiones, ΔMSE/ΔR², retorno en bps y sensibilidad a dependencia temporal. No hacer claim de rentabilidad; solo si el efecto supera esta prueba, diseñar después una simulación neta de ejecución.

### Criterios de aceptación

- Ningún `label_end_time` del train alcanza el primer timestamp del test; tests automáticos cubren igualdad, solapamiento y cambio de sesión.
- Reproducción determinista del dataset/evaluador y hashes registrados.
- Métrica primaria fijada previamente; comparación pareada en mismas observaciones; incertidumbre respeta segmentos temporales.
- Considerar apoyo a H1 solo si ΔR² OOS supera el umbral mínimo preespecificado de +0.10%, el intervalo de incertidumbre no incluye cero, el contraste primario sobrevive el ajuste definido y la mejora no depende de una sola sesión. Si no, concluir no demostrado o evidencia en contra, según intervalo y magnitud.
- Aun con aceptación, esto demostraría predicción estadística, no rentabilidad.

**Estimación de implementación:** aproximadamente 0.5–1.5 días de ingeniería para purga temporal, pruebas focalizadas e inferencia respetuosa de sesiones; 0.5 día para congelar protocolo y generar/revisar una evaluación reproducible. La duración de captura depende de horarios y calidad del feed; como mínimo se necesita un período futuro reservado con varias sesiones, no una nueva partición del mismo holdout ya observado. No es una cotización ni incluye simulador de ejecución.

## H. Archivos que sería necesario modificar en la siguiente etapa

No se modificaron en esta auditoría. Para el paso mínimo:

| Archivo | Cambio previsto | Motivo |
|---|---|---|
| `scripts/evaluate_models_oos_v3.py` | Versión nueva/identificada del evaluador: purga del holdout por `timestamp + H`; inferencia que preserve bloques y límites de sesión/fold. | Corregir contaminación temporal y dependencia en HAC/bootstrap. |
| `tests/test_evaluate_models_oos_v3.py` *(nuevo, si no existe en el ZIP)* | Pruebas sintéticas pequeñas para la frontera de holdout, labels que cruzan sesión, gaps y bootstrap/HAC por bloques. | Evitar que el mismo error regrese. |
| `NAVIER_V3_PROTOCOL.md` | Addendum versionado que declare la corrección, el dataset nuevo reservado, el contraste primario y reglas de decisión. | El holdout histórico ya fue consultado; debe protegerse una evaluación futura. |
| `scripts/run_phase5_evaluation.py` | Permitir salida nueva con nombre/versionado y registrar nuevas versiones/configuración sin sobrescribir resultados anteriores. | Preservar la evidencia ya guardada y reproducir el nuevo análisis. |
| `docs/v3_freeze_manifest.md` *(o manifiesto nuevo)* | Registrar hashes del protocolo, código, datos y pruebas para la evaluación corregida. | Trazabilidad del nuevo run. |
| `scripts/build_research_dataset_v3.py` *(solo si hace falta para el holdout nuevo)* | Añadir metadatos explícitos de `label_end_time`/validez, manteniendo por sesión y conservando raw. | Facilitar comprobación de purge y procedencia temporal. |

No hay motivo para modificar ahora los notebooks 001/001.5, reconstruir módulos ya existentes ni crear otro modelo. No se recomienda retocar features hasta que una evaluación independiente y no contaminada resuelva la incertidumbre.

## Comandos y límites de esta auditoría

- Inventario directo del ZIP con `zipfile`; no se descargaron datos.
- Extracción temporal del ZIP en `_audit_copy` dentro del workspace para ejecutar pruebas aisladas.
- Suite: `python -m pytest -q -p no:cacheprovider`.
- Resampleo: `python scripts/resample_l2_1s.py --input data/kraken/btc_usdt_l2.parquet --output data/kraken/_audit_reproduced_1s.parquet`.
- Evaluación V3: llamada en memoria a `evaluate_dataset_v3(..., holdout_ratio=.20, k_folds=5, purge=10, embargo=10, seed=42)` sobre el Parquet congelado; salidas contrastadas con `results/phase5_v3/oos_evaluation_results.json`.
- No se ejecutaron notebooks enteros, capturas nuevas, conexiones de trading ni pruebas sobre el ZIP original. No se escribieron resultados sobre el código fuente del proyecto.

**Clasificación final:** existencia del pipeline y resultados archivados, **demostrada**; reproducción del resampler corto y evaluación numérica V3, **demostrada**; aporte predictivo incremental de NAVIER en BTC real, **no demostrado**; rentabilidad neta, **no evaluada**. El holdout V3 reportado no es confirmatorio válido por contaminación temporal.
