# NAVIER V2 — Plan de implementación y validación experimental

## Mandato general

Actúa como ingeniero cuantitativo sénior y responsable de reproducibilidad científica del proyecto NAVIER.

El objetivo de NAVIER V2 es investigar si las variables inspiradas en dinámica de fluidos aportan información predictiva incremental sobre el movimiento del mid-price de BTC en un libro de órdenes L2, frente a modelos convencionales de microestructura.

No debes asumir que la hipótesis es correcta. El resultado válido puede ser positivo, negativo o inconcluso.

Trabaja sobre el repositorio existente, inspeccionando primero su estructura y los archivos reales. No inventes módulos, funciones, resultados ni pruebas. No sobrescribas datos originales. No cambies fórmulas de NAVIER V0.1. Mantén separadas las mejoras técnicas, las variantes experimentales y los resultados de cada versión.

La implementación se divide en seis fases con criterios de aceptación explícitos.

---

# FASE 0. Auditoría inicial y protección del estado existente

Antes de modificar archivos:

1. Inspecciona la estructura del repositorio y lee:
   - La documentación de NAVIER 001.8 y 001.9.
   - El esquema de datos.
   - El capturador de Kraken.
   - El resampler.
   - El módulo de features.
   - Las pruebas unitarias y de integración.
   - El manifiesto y los metadatos del dataset actual, si existen.

2. Ejecuta la suite de pruebas existente y registra los resultados reales:
   - Número de pruebas aprobadas, fallidas y omitidas.
   - Duración.
   - Errores o advertencias relevantes.
   - Versión de Python y dependencias importantes.

3. Verifica que el archivo crudo de Kraken siga intacto y que su hash coincida con el manifiesto original, si existe.

4. Comprueba que la salida resampleada pueda reproducirse a partir de la entrada original. Registra los hashes de entrada y salida, la configuración y las versiones de dependencias.

5. No afirmes que NAVIER 001.9 está auditado independientemente hasta haber inspeccionado y reproducido la evidencia.

**Criterio de aceptación:** estado inicial documentado, pruebas reproducibles, datos originales protegidos y diferencias entre resultados esperados y observados identificadas.

Si falla una prueba previa o cambia inesperadamente un archivo de referencia, detente y explica el problema antes de continuar.

---

# FASE 1. Ensayo piloto de selección del par

## Objetivo

Determinar si BTC/USDT o BTC/USD en Kraken ofrece condiciones de captura más adecuadas para el experimento. No decidir por reputación del exchange ni por suposiciones generales sobre cuál es el par más líquido.

## Diseño de captura

1. Verifica que ambos pares estén disponibles y que el canal L2 utilizado proporcione datos comparables.
2. Utiliza el mismo exchange, profundidad del libro, configuración del capturador y método de resampleo.
3. Realiza capturas piloto de 15 minutos por par, como mínimo, para comprobar el funcionamiento inicial.
4. Si se capturan simultáneamente, registra cada flujo por separado y controla diferencias de suscripción, latencia y procesamiento. Si se capturan en momentos diferentes, reconoce que la comparación queda confundida por el cambio de condiciones de mercado.
5. No trates una sola pareja de ventanas como evidencia suficiente para elegir definitivamente el mercado. Si la diferencia es pequeña o cambia según la sesión, amplía el piloto con ventanas comparables adicionales.

## Métricas que deben registrarse

Para cada par y sesión, informa:

- Spread en puntos básicos: mediana, percentil 95 y distribución.
- Profundidad nominal agregada de los diez niveles de compra y venta, expresada en una moneda común y calculada de manera consistente.
- Frecuencia de actualizaciones por segundo y distribución de las ráfagas.
- Antigüedad del último estado del libro en cada segundo.
- Porcentaje de intervalos observados, arrastrados e inválidos.
- Gaps, desconexiones, errores de checksum y tiempo necesario para recuperar un libro válido.
- Cantidad de segundos utilizables después de aplicar los criterios de calidad.
- Diferencias entre las métricas de ambos pares a lo largo de las ventanas comparables.

No confundas mensajes recibidos con transacciones ejecutadas. El canal L2 registra actualizaciones del libro, no necesariamente operaciones de compraventa.

## Regla de decisión

La comparación entre pares debe separar las diferencias de mercado de las diferencias de calidad de captura.

1. Verifica los símbolos y mercados disponibles en Kraken mediante documentación oficial y metadatos observados del exchange. No asumas que BTC/USDT y BTC/USD tienen idéntica disponibilidad, precisión, tick size o comportamiento del libro.
2. Utiliza la misma profundidad en niveles y el mismo procedimiento de reconstrucción del libro. Registra las diferencias inevitables de configuración.
3. Define cómo convertir la profundidad nominal de ambos pares a una moneda común. Documenta la fuente y el instante de cualquier tipo de cambio utilizado.
4. Distingue las métricas de calidad del flujo de las métricas de liquidez observada. Una menor tasa de mensajes, por sí sola, no demuestra menor liquidez ni peor calidad.
5. Para una comparación exploratoria, utiliza ventanas simultáneas cuando sea técnicamente posible. Si no lo es, documenta la falta de sincronía y evita atribuir causalmente las diferencias al par.
6. Informa resultados por sesión y no únicamente mediante promedios agregados. Muestra la variabilidad entre ventanas y los datos que no pudieron compararse.
7. Las capturas piloto de 15 minutos sirven para verificar el funcionamiento inicial y detectar diferencias operativas. No bastan para afirmar superioridad general ni predictiva de un par.

La selección final debe basarse en criterios de calidad, comparabilidad y pertinencia para la investigación. Si la evidencia no distingue claramente los pares, conserva la decisión como provisional y documenta qué información adicional permitiría resolverla.

**Criterio de aceptación:** informe comparativo reproducible, elección justificada o decisión explícitamente pendiente. No se afirma que el par seleccionado genere mejores predicciones.

---

# FASE 2. Protocolo experimental previo a la captura extensa

Antes de generar una muestra destinada a evaluación predictiva, crea un documento versionado de preespecificación.

Debe fijar:

1. Par y exchange seleccionados.
2. Profundidad del libro y frecuencia de resampleo.
3. Fechas, horarios y duración de las sesiones.
4. Criterios de calidad, discontinuidad y exclusión.
5. Variables de entrada y fórmulas exactas.
6. Horizonte primario de predicción: 10 segundos.
7. Horizontes secundarios, si se incluyen, identificados como exploratorios.
8. Definición matemática del objetivo y sus unidades.
9. Modelos que se compararán y métrica primaria de comparación.
10. Protocolo de entrenamiento, validación y prueba final.
11. Pruebas estadísticas, ajustes por comparaciones múltiples y criterios para interpretar los resultados.
12. Criterios de éxito, fracaso e inconclusión.
13. Condiciones bajo las que una sesión se considera inválida.
14. Política para cambios de protocolo y registro de desviaciones.

## Protección contra selección retrospectiva

La captura piloto puede utilizarse para evaluar calidad de datos y resolver problemas de ingeniería. No debe reutilizarse inadvertidamente como prueba final si se han tomado decisiones de modelado observando sus resultados predictivos.

El documento debe indicar qué decisiones se han tomado usando el piloto y qué datos quedan reservados para la evaluación final.

**Criterio de aceptación:** protocolo fechado, versionado y congelado antes de consultar los resultados predictivos del conjunto final.

---

# FASE 3. Captura multisesión y control de calidad

## Objetivo

Construir una muestra que cubra condiciones de mercado variadas sin presuponer que unas horas concretas siempre representan alta o baja volatilidad.

## Plan de captura

1. Captura sesiones en diferentes franjas horarias y días.
2. Registra los tiempos del exchange y de recepción por separado.
3. Conserva los mensajes crudos, los metadatos de conexión, los checksums y los eventos de recuperación.
4. Registra la configuración y el estado de cada sesión.
5. Calcula métricas descriptivas de volatilidad, spread, profundidad, actividad y discontinuidades.
6. Documenta los periodos de eventos extraordinarios, sin eliminarlos automáticamente solo porque produzcan resultados incómodos.

No fijes arbitrariamente que dos, doce o veinticuatro horas son suficientes para validar la hipótesis. La duración inicial de captura sirve para desarrollar el pipeline; la suficiencia de la muestra depende de la variabilidad entre sesiones, el número de observaciones efectivamente utilizables y la precisión de las estimaciones.

## Tratamiento de discontinuidades

Distingue entre:

- Ausencia de mensajes sin evidencia de desconexión.
- Estado del libro que ha envejecido más allá del límite permitido.
- Desconexión o reinicio de la conexión.
- Fallo de checksum o pérdida de integridad del libro.
- Nuevo snapshot que restablece un estado válido, pero no recupera la trayectoria perdida.

Conserva siempre los datos originales. Excluye observaciones afectadas según reglas preespecificadas y registra cuántas se pierden y por qué.

No descartes automáticamente toda una sesión por superar un porcentaje universal de gaps. El criterio de calidad debe depender del tipo de prueba, de la duración y ubicación de las discontinuidades y de si estas contaminan las ventanas de features o las etiquetas.

**Criterio de aceptación:** dataset multisesión trazable, resumen de calidad por sesión y exclusiones reproducibles.

---

# FASE 4. Construcción del dataset de investigación

## Resampleo y causalidad

Utiliza el resampler 001.9 como base solo después de verificarlo.

Cada fila de la rejilla temporal debe tener una procedencia inequívoca y conservar la información necesaria para reconstruir su estado. No inventes actualizaciones ni interpretes un libro arrastrado como una observación nueva.

El resampleo causal no demuestra por sí solo que el dataset completo esté libre de fugas. Deben auditarse también todas las transformaciones posteriores.

## Variables convencionales

Construye y valida las variables de referencia necesarias para que NAVIER tenga una comparación justa:

- Spread.
- Profundidad.
- Imbalance del libro.
- Order Flow Imbalance, siempre que pueda calcularse correctamente con los mensajes disponibles.
- Retornos y momentum históricos.
- Volatilidad histórica.

Especifica para cada variable qué datos utiliza, su ventana temporal, sus unidades y el instante en que está disponible.

## Variables NAVIER

Conserva las fórmulas originales de V0.1 sin modificarlas.

Cualquier alternativa debe tener una identidad experimental distinta, con fórmula, motivación, parámetros y pruebas propios. Las variables normalizadas o regularizadas no pueden reemplazar silenciosamente a sus equivalentes originales.

Revisa especialmente:

- Unidades y normalización de los gradientes del libro.
- Cálculo causal de las derivadas de imbalance.
- Sensibilidad numérica del proxy de Reynolds.
- Definición dimensional de cualquier escala de profundidad o distancia.

No llames «distancia en bps» a un índice de niveles ponderado si no se ha definido una conversión dimensional correcta.

## Objetivo primario

Mantén como objetivo principal el retorno del mid-price a 10 segundos, con una definición matemática inequívoca y causalmente alineada.

Distingue entre:

- Retorno futuro nominal, expresado en puntos básicos.
- Objetivo normalizado por volatilidad histórica.
- Instante en el que la etiqueta futura queda disponible para entrenamiento.

La volatilidad utilizada para normalizar el objetivo debe estimarse exclusivamente con información disponible en el instante de origen. Define el calentamiento, los valores casi nulos, las discontinuidades y las condiciones de exclusión.

No utilices interpolación para fabricar precios futuros ausentes. No rellenes silenciosamente ventanas contaminadas por gaps.

### Especificación temporal y dimensional del objetivo

La implementación debe distinguir explícitamente el instante de origen de la observación y el instante en que se conoce su etiqueta futura.

Para un horizonte primario de 10 segundos, define el retorno nominal como:

r₁₀(t) = ln(mid(t + 10 s) / mid(t))

Su expresión en puntos básicos es:

r₁₀,bps(t) = 10 000 × r₁₀(t)

Si se utiliza el objetivo normalizado por volatilidad histórica, especifica la fórmula exacta, el estimador de volatilidad, la ventana, las unidades, el calentamiento y el tratamiento de valores nulos o casi nulos. La normalización debe usar exclusivamente información disponible en el instante de origen t.

La preespecificación debe identificar un objetivo primario único y separar los objetivos secundarios o de robustez. Para mantener la comparabilidad con el diseño experimental existente, el retorno normalizado a 10 segundos será el objetivo primario propuesto, sujeto a verificar y documentar su fórmula exacta antes de congelar el protocolo. El retorno nominal en puntos básicos se conservará para interpretar la magnitud de los movimientos.

Para cada observación, registra al menos:

- Tiempo de origen de la predicción.
- Tiempo del último estado válido del libro utilizado.
- Tiempo de disponibilidad de cada feature.
- Tiempo objetivo de la etiqueta y tiempo efectivo en que esta puede calcularse.
- Indicador de validez de la ventana futura.
- Motivo de exclusión, cuando corresponda.

No interpoles mid-prices futuros ausentes ni calcules etiquetas a través de discontinuidades que invaliden la ventana.

### Auditoría de dependencia temporal y prevención de leakage

Una rejilla de un segundo con etiquetas de retorno a diez segundos produce intervalos futuros solapados en observaciones consecutivas. Esto induce dependencia entre etiquetas y errores de predicción, pero no implica automáticamente que la dependencia siga un modelo MA de orden determinado.

La validación debe:

1. Respetar el orden cronológico: entrenar con el pasado y evaluar sobre periodos posteriores.
2. Purgar del entrenamiento las observaciones cuyas etiquetas utilicen información que atraviese el límite temporal de evaluación.
3. Definir cualquier embargo en función del horizonte de etiqueta, la estructura de los bloques y el diseño concreto de validación. Justificar su duración en lugar de adoptar un valor fijo sin análisis.
4. Verificar que la normalización, la imputación, la selección de variables y el ajuste de hiperparámetros se estimen exclusivamente con los datos permitidos en cada bloque de entrenamiento.
5. Comprobar que las ventanas de features no incorporen información futura. El uso de historia anterior al comienzo de un bloque de prueba puede ser válido si estaba disponible en tiempo real y el protocolo lo permite.
6. Informar el número de observaciones eliminadas por purgado, embargo, calentamiento y discontinuidades.
7. Evaluar la sensibilidad de la inferencia estadística a supuestos razonables de dependencia temporal, sin elegir retrospectivamente el método que produzca el resultado más favorable.

La auditoría debe demostrar estas propiedades mediante pruebas y verificaciones de código. No basta con que el resampler sea causal.

El uso de una separación temporal correcta no garantiza por sí solo que las estimaciones estadísticas sean independientes ni que el tamaño efectivo de la muestra coincida con el número de filas.

**Criterio de aceptación:** dataset de features y objetivos con trazabilidad, unidades documentadas, pruebas de causalidad y exclusiones verificables.

---

# FASE 5. Evaluación predictiva fuera de muestra

## Modelos que se compararán

Preespecifica al menos estas familias:

- **Modelo A:** spread, profundidad y volatilidad.
- **Modelo B:** variables convencionales de microestructura, incluyendo imbalance, OFI y momentum.
- **Modelo C:** Modelo B más las variables originales NAVIER V0.1.
- **Modelo D:** Modelo B más las variantes experimentales NAVIER V0.2.

Si se estudian rezagos adicionales o familias alternativas, documenta previamente por qué son necesarios y cuántas hipótesis se están contrastando.

El propósito principal es comprobar si C mejora a B y si D aporta mejoras adicionales reproducibles. No basta con que NAVIER supere a una línea base débil.

## Validación temporal

Utiliza una evaluación cronológica walk-forward, con entrenamiento exclusivamente en el pasado y predicción sobre periodos posteriores.

Aplica purgado cuando las etiquetas de diferentes observaciones compartan intervalos temporales, y define un embargo apropiado. No permitas que datos futuros entren en el entrenamiento de un bloque anterior.

La normalización, selección de variables, imputación, selección de hiperparámetros y ajuste de regularización deben realizarse únicamente dentro del conjunto de entrenamiento correspondiente.

Mantén un hold-out final que no se utilice para elegir modelos ni modificar fórmulas. Si se consulta para tomar decisiones, deja de ser una evaluación final intacta y será necesario reservar datos posteriores.

## Evaluación estadística

Define de antemano una métrica primaria y reporta, como mínimo:

- Rendimiento fuera de muestra de cada modelo.
- Diferencia pareada de rendimiento entre los modelos relevantes.
- Magnitud e incertidumbre de las mejoras.
- Significación estadística con un método que tenga en cuenta la dependencia temporal.
- Corrección por comparaciones múltiples cuando corresponda.
- Estabilidad de los resultados entre sesiones y regímenes.
- Número de observaciones y sesiones efectivamente utilizadas.

El test de Diebold-Mariano, las correcciones de muestra finita y los estimadores de varianza robustos pueden ser apropiados, pero deben justificarse según la dependencia de los errores y el diseño concreto. No declares automáticamente que existe una estructura MA exacta solo porque el horizonte de las etiquetas sea de diez segundos.

No uses un valor p aislado como criterio de éxito universal. Una mejora debe ser cuantitativamente relevante, reproducible y estable; si no lo es, el resultado debe describirse como débil, negativo o inconcluso según la evidencia.

### Métrica primaria y regla de comparación

Antes de evaluar el conjunto final, especifica y congela una métrica primaria única para comparar los modelos sobre el objetivo primario.

Como propuesta inicial, utiliza el error cuadrático medio (MSE) fuera de muestra del retorno normalizado a 10 segundos. Documenta su fórmula, las unidades del objetivo, el tratamiento de valores no válidos y la regla de agregación entre bloques y sesiones.

Para cada comparación relevante, especialmente C frente a B y D frente a B:

- Evalúa ambos modelos sobre las mismas observaciones válidas.
- Calcula la diferencia pareada de la métrica primaria.
- Informa el rendimiento individual de cada modelo y la magnitud de la diferencia.
- Estima la incertidumbre de la diferencia mediante un método compatible con la dependencia temporal y la estructura de sesiones.
- Informa resultados por sesión y agregados, para detectar si una mejora global depende de unas pocas ventanas.
- Conserva métricas secundarias, como el error sobre retornos nominales en puntos básicos, para interpretar la magnitud práctica del error.

Si se utiliza una prueba de Diebold-Mariano, justifica la definición de la pérdida, la construcción de las diferencias de pérdida y el estimador de varianza empleado. Considera la dependencia inducida por el solapamiento de etiquetas y otras fuentes observadas de autocorrelación. No supongas automáticamente un proceso MA exacto ni selecciones el número de rezagos después de observar qué especificación favorece a NAVIER.

Preespecifica los contrastes principales y el tratamiento de comparaciones múltiples. Las exploraciones adicionales deben etiquetarse como tales y no convertirse retrospectivamente en hipótesis confirmatorias.

### Criterios de interpretación

La mejora predictiva debe evaluarse en términos de magnitud, incertidumbre, estabilidad entre sesiones y robustez ante decisiones metodológicas justificadas.

No declares éxito únicamente porque un valor p sea inferior a un umbral. Tampoco declares equivalencia o ausencia de efecto únicamente porque un contraste no resulte significativo.

Si la muestra no permite distinguir una mejora relevante de la incertidumbre, clasifica el resultado como inconcluso. Cuando sea posible, define antes de la evaluación un umbral de relevancia práctica y un análisis de precisión o potencia que justifique si el volumen de datos disponible permite evaluar ese umbral.

La métrica primaria no debe cambiarse después de consultar los resultados del conjunto final. Cualquier desviación del protocolo debe registrarse, explicarse y distinguirse del análisis confirmatorio original.

**Criterio de aceptación:** informe reproducible de comparación fuera de muestra, sin selección retrospectiva del modelo ganador y sin afirmaciones que excedan los resultados.

---

# FASE 6. Evaluación económica posterior

Esta fase solo se inicia si la evaluación predictiva proporciona evidencia suficientemente sólida.

Investiga por separado si la información predictiva puede convertirse en una decisión económica realista. Incorpora, según el diseño de ejecución:

- Spread de entrada y salida.
- Comisiones reales aplicables.
- Deslizamiento y latencia.
- Restricciones de ejecución y liquidez disponible.
- Rotación y frecuencia de operaciones.
- Sensibilidad a los supuestos de ejecución.

No conviertas automáticamente una mejora en la predicción del mid-price en una estrategia rentable. Una señal puede ser estadísticamente útil y no generar beneficios netos.

**Criterio de aceptación:** evaluación económica separada y documentada, sin confundir predicción del precio con rentabilidad realizable.

---

# Organización, entregables y control de cambios

Antes de crear módulos nuevos, inspecciona la estructura real y reutiliza los componentes existentes cuando sea apropiado.

Entrega documentación versionada que incluya:

1. Informe de auditoría inicial.
2. Informe comparativo del piloto de pares.
3. Protocolo experimental congelado.
4. Manifiestos y hashes de las capturas.
5. Informe de calidad por sesión.
6. Especificación y auditoría del dataset de features.
7. Informe de evaluación predictiva, cuando exista muestra suficiente.
8. Registro de cambios, desviaciones y decisiones.

No sobrescribas la captura cruda ni alteres las fórmulas de NAVIER V0.1. Toda modificación debe ser identificable y reproducible.

## Reglas de ejecución

- Trabaja en el orden indicado.
- No declares una fase completada sin mostrar evidencia verificable.
- No inventes resultados para completar un informe.
- No confundas pruebas de ingeniería con evidencia predictiva.
- No cambies el par, el horizonte primario o los criterios de descarte sin documentar la razón.
- Si aparece un problema que invalida una fase, detente, explica el problema y propone la corrección antes de continuar.
- Separa los resultados observados, las inferencias y las decisiones pendientes.
- No realices operaciones de trading ni uses credenciales de negociación.

## Resultado esperado

NAVIER V2 debe ser un experimento reproducible que permita responder, con evidencia fuera de muestra, a una pregunta concreta:

**¿Las variables inspiradas en dinámica de fluidos aportan información predictiva incremental, estable y medible sobre un modelo convencional sólido de microestructura L2?**

No se presupone que la respuesta sea afirmativa.

Empieza por la Fase 0 y entrega su informe antes de pasar a la Fase 1. No avances automáticamente a la siguiente fase si hay criterios de aceptación incumplidos o decisiones que requieren aprobación del responsable del proyecto.