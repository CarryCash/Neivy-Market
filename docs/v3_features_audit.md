# NAVIER V3 — Informe de Auditoría y Construcción del Dataset de Investigación (Fase 4)

**Fecha de emisión inicial:** 2026-10-24  
**Fecha de adenda metodológica y dictamen:** 2026-10-24  
**Etapa:** Fase 4 — Construcción y Auditoría Criptográfica, Causal, Multivariada y de Colas del Dataset V3  
**Estado:** AUDITORÍA AMPLIADA COMPLETADA — EVALUACIÓN OOS BLOQUEADA HASTA APROBACIÓN FORMAL  
**Símbolo:** BTC/USD · Kraken Spot WebSocket API v2 · Profundidad L2 (10 niveles)  
**Dataset analizado:** [data/research_dataset_v3.parquet](file:///C:/Users/USER/Downloads/navier_lab_project/navier_lab_project/data/research_dataset_v3.parquet)  
**Hash SHA-256 (Dataset):** `5e7139209e8ee62bfbd6a04f6387e8ba987894f98da75372b2a5a15645c0f7d8`  
**Manifiesto de trazabilidad:** [data/research_dataset_v3.manifest.json](file:///C:/Users/USER/Downloads/navier_lab_project/navier_lab_project/data/research_dataset_v3.manifest.json)  

---

> [!IMPORTANT]
> **Preservación estricta del protocolo de investigación:**  
> Ningún modelo predictivo ha sido entrenado ni evaluado durante esta fase. No se ha invocado `evaluate_dataset_v3()`, no se han calculado residuos predictivos OOS, no se han modificado hiperparámetros ni alterado los umbrales preespecificados ($\delta_{\min} = 0.0010$, $\alpha = 0.05$). Todos los archivos congelados en la Fase 3 permanecen intactos con sus hashes criptográficos verificados.

---

## 1. Preservación Criptográfica y Estado de Artefactos Congelados

Se verificaron todos los artefactos de código y protocolo pre-registrados frente a [docs/v3_freeze_manifest.md](file:///C:/Users/USER/Downloads/navier_lab_project/navier_lab_project/docs/v3_freeze_manifest.md), así como las capturas raw frente a [docs/v3_capture_manifest.md](file:///C:/Users/USER/Downloads/navier_lab_project/navier_lab_project/docs/v3_capture_manifest.md):

| Componente | Archivo | Hash SHA-256 Esperado | Hash SHA-256 Verificado | Estado |
|---|---|---|---|:---:|
| **Protocolo Científico** | [NAVIER_V3_PROTOCOL.md](file:///C:/Users/USER/Downloads/navier_lab_project/navier_lab_project/NAVIER_V3_PROTOCOL.md) | `0183b474253d5b6f50f25aba7e463a925a4ff5183da99a3648736dd93095114a` | `0183b474253d5b6f50f25aba7e463a925a4ff5183da99a3648736dd93095114a` | INTACTO |
| **Pipeline de Features** | [navier_lab/features.py](file:///C:/Users/USER/Downloads/navier_lab_project/navier_lab_project/navier_lab/features.py) | `1b642ebfe827e9348f8ded67f9e5f706d0f6599074156094fb73131a2fa853db` | `1b642ebfe827e9348f8ded67f9e5f706d0f6599074156094fb73131a2fa853db` | INTACTO |
| **Esquema y Configuración** | [navier_lab/schema.py](file:///C:/Users/USER/Downloads/navier_lab_project/navier_lab_project/navier_lab/schema.py) | `a34cec8a9d57b3bdcf8c5b7e803452b33e288b238cba2f398c66f0fa8cf80e1a` | `a34cec8a9d57b3bdcf8c5b7e803452b33e288b238cba2f398c66f0fa8cf80e1a` | INTACTO |
| **Resampleador Causal L2** | [navier_lab/resampler.py](file:///C:/Users/USER/Downloads/navier_lab_project/navier_lab_project/navier_lab/resampler.py) | `220be7754e5377f69d4539b400435f40a6e96257687237e1ac8cf957e3de7f35` | `220be7754e5377f69d4539b400435f40a6e96257687237e1ac8cf957e3de7f35` | INTACTO |
| **Motor de Evaluación OOS** | [scripts/evaluate_models_oos_v3.py](file:///C:/Users/USER/Downloads/navier_lab_project/navier_lab_project/scripts/evaluate_models_oos_v3.py) | `52f566f12bc2728eacebeef97ebcce04133e68d3166bcdedfd9c6d5f7b67bedb` | `52f566f12bc2728eacebeef97ebcce04133e68d3166bcdedfd9c6d5f7b67bedb` | INTACTO |
| **Capturador L2 Kraken** | [scripts/capture_kraken_l2.py](file:///C:/Users/USER/Downloads/navier_lab_project/navier_lab_project/scripts/capture_kraken_l2.py) | `d7f01a500f54ac790262ad41806394a8288189e5d31c55f012a57f903c681712` | `d7f01a500f54ac790262ad41806394a8288189e5d31c55f012a57f903c681712` | INTACTO |
| **Suite de Pruebas Congelada** | [tests/test_features_v3.py](file:///C:/Users/USER/Downloads/navier_lab_project/navier_lab_project/tests/test_features_v3.py) | `9202eb588baa451c2cb53e8be6ba25bb18d08a8195a339eac6f2818074763118` | `9202eb588baa451c2cb53e8be6ba25bb18d08a8195a339eac6f2818074763118` | INTACTO |

Las 7 capturas independientes originales `.parquet` en `data/v3_validation/sessions/` coinciden exactamente con los hashes de [v3_capture_manifest.md](file:///C:/Users/USER/Downloads/navier_lab_project/navier_lab_project/docs/v3_capture_manifest.md).

---

## 2. Construcción Independiente por Sesión y Jerarquía de Descartes

El pipeline procesa de forma estrictamente aislada cada una de las 7 sesiones independientes. En ningún momento se concatenan datos antes de calcular los predictores y las etiquetas causales.

### 2.1 Jerarquía Determinista de Reglas de Exclusión

Para eliminar toda ambigüedad entre categorías exclusivas e indicadores superpuestos, se establece formalmente el orden de prelación determinista para asignar la **causa raíz primaria** a cada fila descartada:

$$\text{Warmup (60s)} \succ \text{Fin de Sesión (10s)} \succ \text{Gap Directo} \succ \text{Gap Futuro (10s)} \succ \text{Staleness Futuro (>1s)} \succ \text{Historia Corrupta (60s)} \succ \text{Suelo Volatilidad} \succ \text{NaN Residual}$$

1. **Prioridad 1 — Calentamiento inicial (60 s):** Primeras 60 observaciones por sesión (cálculo de $\hat{\sigma}_{60}$ y $\mathrm{OFI}_5$).
2. **Prioridad 2 — Fin de sesión (10 s):** Últimas 10 observaciones por sesión (evita horizonte futuro más allá del cierre).
3. **Prioridad 3 — Discontinuidad directa (`GAP_DISCONTINUITY`):** Bins donde el intervalo $(T-1, T]$ superó el umbral de gap ($>3.0$ s) o reconexión del WebSocket.
4. **Prioridad 4 — Fuga por gap en horizonte futuro $(t, t+10]$:** Invalida causalmente el target $y_t$.
5. **Prioridad 5 — Obsolescencia futura (`staleness_ms > 1000` ms) en $(t, t+10]$:** Invalida el target por libro no actualizado.
6. **Prioridad 6 — Historia retrospectiva corrompida en $[t-60, t]$:** Gaps previos o $>20\%$ de estados arrastrados (`CARRIED_FORWARD`).
7. **Prioridad 7 — Suelo de volatilidad causal ($\hat{\sigma}_{60} < 0.01$ bps):** Invalida el target ante denominador singular.
8. **Prioridad 8 — NaN residual de predictores:** Cualquier otra ausencia no capturada en las anteriores.

---

### 2.2 Tabla A: Partición Mutuamente Excluyente de Descartes (Suma Exacta = 3 192)

Cada observación descartada pertenece a **exactamente una** categoría según la jerarquía de prelación. La suma de las columnas coincide rigurosamente con el total de filas descartadas ($16\ 750 - 13\ 558 = 3\ 192$):

| Sesión | Bins 1s Totales | **Válidas Retenidas** | Total Descartes | Warmup (60s) | Fin Sesión (10s) | Gap Directo | Gap Futuro (10s) | Staleness Futuro (>1s) | Hist. Corrupta (60s) | Vol < 0.01 bps | NaN Residual |
|:---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **01** | 2 369 | **2 259** | 110 | 60 | 10 | 0 | 0 | 40 | 0 | 0 | 0 |
| **02** | 2 396 | **1 897** | 499 | 60 | 10 | 187 | 50 | 39 | 152 | 0 | 1 |
| **03** | 2 391 | **1 286** | 1 105 | 60 | 10 | 715 | 109 | 43 | 167 | 0 | 1 |
| **04** | 2 399 | **2 036** | 363 | 60 | 10 | 42 | 20 | 111 | 118 | 0 | 2 |
| **05** | 2 398 | **2 194** | 204 | 60 | 10 | 0 | 0 | 134 | 0 | 0 | 0 |
| **06** | 2 399 | **2 068** | 331 | 60 | 10 | 0 | 0 | 260 | 0 | 1 | 0 |
| **07** | 2 398 | **1 818** | 580 | 60 | 10 | 0 | 0 | 510 | 0 | 0 | 0 |
| **TOTAL** | **16 750** | **13 558** | **3 192** | **420** | **70** | **944** | **179** | **1 137** | **437** | **1** | **4** |

$$\sum \text{Categorías Exclusivas} = 420 + 70 + 944 + 179 + 1137 + 437 + 1 + 4 = \mathbf{3\ 192} \quad (\text{Identidad exacta}).$$

---

### 2.3 Tabla B: Indicadores de Calidad Superpuestos (Incidencia Bruta de Banderas)

Muestra cuántas veces se activó cada condición patológica de forma aislada en cada bin de la serie (múltiples banderas pueden activarse simultáneamente en una misma fila, generando un total acumulado de 6 588 incidencias):

| Sesión | Warmup (60s) | Fin Sesión (10s) | Gap Directo | Gap Futuro (10s) | Staleness Futuro (>1s) | Hist. Corrupta (60s) | Vol < 0.01 bps | Total Banderas Superpuestas |
|:---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **01** | 60 | 10 | 0 | 0 | 40 | 0 | 0 | 110 |
| **02** | 60 | 10 | 187 | 232 | 272 | 377 | 0 | 1 138 |
| **03** | 60 | 10 | 759 | 875 | 920 | 1 050 | 0 | 3 674 |
| **04** | 60 | 10 | 42 | 60 | 181 | 160 | 0 | 513 |
| **05** | 60 | 10 | 0 | 0 | 140 | 0 | 0 | 210 |
| **06** | 60 | 10 | 0 | 0 | 268 | 0 | 1 | 339 |
| **07** | 60 | 10 | 0 | 0 | 531 | 3 | 0 | 604 |
| **TOTAL** | **420** | **70** | **988** | **1 167** | **2 352** | **1 590** | **1** | **6 588** |

**Interpretación del solapamiento:**  
En la Sesión 03, los 759 bins con gap directo generan mecánicamente un arrastre de 875 bins con gap futuro en $(t, t+10]$ y 1 050 bins con ventana histórica de 60 s invalidada. Esta cascada de contaminación explica por qué la suma de banderas superpuestas alcanza 6 588, mientras que el conteo físico de bins descartados es estrictamente 3 192.

---

## 3. Calidad de Datos, Esquema y Regla de Muestra Común

- **Total de filas consolidadas:** 13 558 observaciones comunes.
- **Total de columnas:** 51 variables.
- **Valores nulos (`NaN`):** **0** en todas las 51 columnas.
- **Valores infinitos (`±Inf`):** **0** en todas las variables numéricas.
- **Claves duplicadas `(session_id, timestamp)`:** **0**.
- **Monotonicidad temporal:** Verificada y estrictamente creciente en cada sesión.
- **Rango temporal consolidado:** Desde `2026-10-22 16:59:53 UTC` hasta `2026-10-23 18:54:35 UTC`.
- **Cobertura común confirmatoria:** 100.00% (13 558 / 13 558 filas) compartidas por todos los modelos (`Model_B`, `Model_B_plus`, `Model_B_plusplus`, `Model_B_tripleplus`, `Model_E`, y `Model_E_H1a`).

---

## 4. Diagnóstico de Colas Extremas y Mecanismo Físico de la Curtosis

### 4.1 Censo Cuantitativo de Observaciones Extremas

El objetivo primario está formalizado por:
$$y(t) = \frac{\ln\left(\frac{\mathrm{mid}(t+10)}{\mathrm{mid}(t)}\right) \times 10^4}{\hat{\sigma}_{60,\mathrm{bps}}(t) \times \sqrt{10}} = \frac{y_{\mathrm{bps}}(t)}{\hat{\sigma}_{60,\mathrm{bps}}(t) \times \sqrt{10}}$$

Distribución de umbrales en el dataset ($N = 13\ 558$):

| Umbral de Cola | Observaciones | % Muestra | Sesión 01 | Sesión 02 | Sesión 03 | Sesión 04 | Sesión 05 | **Sesión 06** | **Sesión 07** |
|---|---:|---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| $|y| > 2.0$ | 1 889 | 13.93% | 231 | 196 | 134 | 224 | 229 | **392** | **483** |
| $|y| > 3.0$ | 702 | 5.18% | 85 | 66 | 50 | 79 | 67 | **156** | **199** |
| $|y| > 5.0$ | 167 | 1.23% | 25 | 9 | 10 | 13 | 20 | **38** | **52** |
| $|y| > 10.0$ | 45 | 0.33% | 2 | 0 | 0 | 0 | 0 | **17** | **26** |
| $|y| > 20.0$ | 28 | 0.21% | 0 | 0 | 0 | 0 | 0 | **10** | **18** |
| $|y| > 50.0$ | 15 | 0.11% | 0 | 0 | 0 | 0 | 0 | **5** | **10** |

```
Quantiles empíricos de y:
  Q( 0.01%): -107.2124 | Q( 0.10%): -20.8203 | Q( 1.00%):  -4.1510 | Q( 5.00%):  -2.2595
  Q(25.00%):   -0.6975 | Q(50.00%):   0.0000 | Q(75.00%):  +0.6581 | Q(95.00%):  +2.4221
  Q(99.00%):   +4.4014 | Q(99.90%): +10.5305 | Q(99.99%): +72.4186
```

---

### 4.2 Mecanismo Físico: Movimiento Real de Precio sobre Libro en Reposo

Inspección de las observaciones con mayor ratio $|y|$ en el dataset:

| Sesión | Timestamp (UTC) | Mid Price | $y_{\mathrm{bps}}$ | $\hat{\sigma}_{60,\mathrm{bps}}$ | Denominador ($\sigma_{60} \sqrt{10}$) | Target $y$ | Spread (bps) | Updates/s |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| **S07** | `2026-10-23 18:46:04` | 81 396.05 | **−3.5143** | **0.010366** | 0.03278 | **−107.212** | 0.0123 | 2 |
| **S07** | `2026-10-23 18:46:05` | 81 396.05 | **−3.5143** | **0.010366** | 0.03278 | **−107.212** | 0.0123 | 2 |
| **S07** | `2026-10-23 18:40:57` | 81 396.05 | **+3.1078** | **0.010357** | 0.03275 | **+94.886** | 0.0123 | 7 |
| **S06** | `2026-10-23 17:52:08` | 81 547.35 | **−5.5811** | **0.019290** | 0.06099 | **−91.492** | 0.0123 | 8 |
| **S07** | `2026-10-23 18:40:56` | 81 396.05 | **+2.4200** | **0.010357** | 0.03275 | **+73.886** | 0.0123 | 10 |

**Hallazgos técnicos del mecanismo:**
1. **Movimientos reales del mercado:**  
   Un retorno $y_{\mathrm{bps}} = -3.51$ bps representa una variación de precio de $\$28.60$ USD sobre un activo de $\$81\ 396$ USD en 10 segundos. No es un error de checksum ni una anomalía de datos del WebSocket.
2. **Amplificación por reposo de libro:**  
   En las sesiones 6 y 7 (final de la jornada, 17:34–18:54 UTC), la actividad de actualización se redujo a 40–54 updates/s (frente a 77–96 updates/s en las sesiones 1–4). Esto produjo lapsos de 60 segundos con volatilidad casi nula ($\hat{\sigma}_{60} \approx 0.0104$ bps), apenas por encima del suelo causal de $0.01$ bps. Al ocurrir un salto de precio estándar sobre un libro en reposo, el cociente estalla a magnitudes $|y| > 90$.
3. **Concentración asimétrica en las últimas dos sesiones:**  
   De las 45 observaciones con $|y| > 10$, **43 ocurren en las Sesiones 06 y 07** (95.6%), 2 en la Sesión 01 y **0 en las Sesiones 02, 03, 04 y 05**.

---

### 4.3 Impacto en la Varianza Global y Procedimiento de Clipping

En una pérdida cuadrática estándar $\mathrm{MSE} = \frac{1}{N} \sum y_i^2$:
- $\mathrm{MSE}_{\mathrm{naive}} = 10.5803$.
- **La observación más extrema sola ($y = -107.21$)** contribuye con $0.8478$ al MSE global (**8.01% de toda la varianza muestral**).
- **Las 10 observaciones más extremas** aportan el **53.24% de la varianza total**.
- **Las 50 observaciones más extremas** aportan el **81.13% de la varianza total**.

**Consecuencia directa para el evaluador OOS:**  
El script congelado [scripts/evaluate_models_oos_v3.py](file:///C:/Users/USER/Downloads/navier_lab_project/navier_lab_project/scripts/evaluate_models_oos_v3.py#L174-L175) implementa `clip_sd = 5.0` **exclusivamente sobre los predictores estandarizados $X$**, pero **no recorta el target $y$**.  
Dado que las sesiones 6 y 7 se ubican cronológicamente en los bloques finales de validación (Split 4 y Holdout del 20%), el error cuadrático medio en el holdout será altamente sensible a si los modelos predicen o neutralizan adecuadamente estas observaciones en régimen de reposo.

> [!CAUTION]
> **Decisión metodológica inmutable:**  
> De acuerdo con el protocolo preregistrado, **está estrictamente prohibido eliminar, censurar o alterar retroactivamente el target** de estas observaciones para buscar métricas más estables. Su origen físico queda plenamente diagnosticado y justificado.

---

## 5. Auditoría de Colinealidad, Condicionamiento de Matriz y Correlación de Rangos

### 5.1 Correlación Lineal (Pearson) frente a Monotonía de Rangos (Spearman)

| Par de Variables | Pearson ($r$) | Spearman ($\rho$) | Diagnóstico Cuantitativo |
|---|---:|---:|---|
| `v03_pnpc_k3` vs `ofi_5` | **+0.4352** | **+0.9002** | Razón monótona alta preservada por signo; dispersión por profundidad contra |
| `v03_pnpc_k3` vs `ofi_raw_5` | **+0.4959** | **+0.9037** | Correlación monotónica de flujo; modulación no lineal por denominador |
| `v03_pnpc_k3` vs `_ofi_div_depth10` | **+0.3572** | **+0.9037** | Co-ordenación de rangos de penetración; desacoplamiento dimensional en magnitudes |
| `v03_pnpc_k3` vs `imb_full` | **+0.2910** | **+0.6855** | Imbalance local modula pero no colapsa el orden |
| `v03_pnpc_k3` vs `depth_log` | **−0.1107** | **−0.1728** | Independencia lineal y de rangos frente a profundidad total |
| `v03_pnpc_k3` vs Target $y$ | **+0.0737** | **+0.2875** | Señal monótona con el target superior a la correlación lineal |

**Análisis de la hipótesis geométrica frente a redundancia:**  
La elevada correlación de Spearman ($\rho \approx 0.90$) evidencia que `v03_pnpc_k3` conserva en gran medida el orden relativo del flujo de órdenes. Sin embargo, la penetración sobre los 3 niveles contrarios (`depth_contra_k3`) comprime o expande la escala de forma no lineal, reduciendo la correlación lineal de Pearson a $r = 0.4352$.  
Un VIF bajo ($3.74$) y una correlación de Pearson moderada confirman que **no existe colinealidad numérica destructiva**, pero **no demuestran por sí mismos que la variable aporte alfa predictivo**. La demostración de si esta variación dimensionalmente corregida contiene información económica real o ruido residual queda delegada exclusivamente al contraste OOS preregistrado de la Fase 5.

---

### 5.2 Condicionamiento Numérico de la Matriz de Diseño ($X^\top X$)

Se examinaron los números de condición $\kappa(A)$ y del operador Gramiano $A^\top A$ con y sin la regularización Ridge preregistrada ($\lambda = 10^{-6} \times N$):

| Modelo | Predictores ($k$) | $\mathrm{Cond}(A)$ | $\mathrm{Cond}(A^\top A)$ | Autovalor Mínimo ($\lambda_{\min}$) | $\mathrm{Cond}(\text{Gram}_{\text{Ridge}})$ |
|---|---:|---:|---:|---:|---:|
| **Model_B** | 9 | 3.58 | 12.83 | 3 100.53 | **12.83** |
| **Model_B_plus** | 12 | 4.47 | 20.02 | 2 666.27 | **20.02** |
| **Model_B_plusplus** | 14 | 5.06 | 25.63 | 2 313.35 | **25.63** |
| **Model_B_tripleplus** | 15 | 5.19 | 26.97 | 2 285.64 | **26.97** |
| **Model_E** | 18 | 5.92 | 35.06 | 1 816.94 | **35.06** |

**Diagnóstico:**  
El número de condición de la matriz completa del Modelo E ($\kappa = 35.06$) es sumamente bajo (valores críticos de mal condicionamiento típicamente superan $10^3$ o $10^4$). La inversión numérica requerida por OLS es determinista, estable y robusta ante perturbaciones numéricas.

---

## 6. Dependencia Temporal, Sensibilidad Newey-West y Potencia Estadística

### 6.1 Dependencia Temporal y Elección del Ancho de Banda Newey-West

La serie de retornos solapados a 10 segundos genera una estructura de correlación temporal que debe ser absorbida por la varianza de largo plazo ($\mathrm{LRV}$). Se evaluó la sensibilidad de la estimación $\mathrm{HAC}$ sobre la pérdida cuadrática del target $y^2$:

| Rezagos ($L$) | $\mathrm{LRV}(y^2)$ | Razón respecto a Varianza ($\Omega / \gamma_0$) | Error Estándar $\mathrm{SE}(\bar{y^2})$ |
|---:|---:|---:|---:|
| $L = 5$ | 190 413.41 | 3.339 | 3.7476 |
| **$L = 10$ (Sensibilidad)** | **246 883.86** | **4.329** | **4.2673** |
| $L = 15$ | 270 512.72 | 4.743 | 4.4668 |
| **$L = 20$ (Primario Preespecificado)** | **282 641.60** | **4.956** | **4.5658** |
| $L = 30$ | 294 656.83 | 5.167 | 4.6619 |
| **$L = 40$ (Sensibilidad)** | **300 311.82** | **5.266** | **4.7064** |
| $L = 60$ | 305 029.66 | 5.349 | 4.7432 |

**Conclusiones metodológicas sobre Newey-West:**
1. A partir de $L = 20$, la curva de $\mathrm{LRV}$ se aplana marcadamente (incremento de solo $+6.2\%$ al duplicar el ancho de banda a $L = 40$). Esto confirma que $L = 20$ captura la totalidad de la estructura de solapamiento $\mathrm{MA}(9)$.
2. No obstante, ante una curtosis muestral elevada, los estimadores $\mathrm{HAC}$ asintóticos pueden presentar distorsiones de tamaño en muestras finitas. Por esta razón, el protocolo preregistra como control confirmatorio complementario el **Stationary Block Bootstrap** ($B = 1000$, longitud media de bloque $1/p = 15$ s), el cual no descansa en supuestos asintóticos de cuarto momento.

---

### 6.2 Demostración Rigurosa de la Potencia Estadística

Bajo el contraste Diebold-Mariano sobre modelos anidados:
$$DM = \frac{\bar{d}}{\sqrt{\hat{\Omega} / N_{\mathrm{eff}}}}, \quad d_t = e_{\mathrm{base},t}^2 - e_{\mathrm{alt},t}^2$$

Para un umbral de futilidad $\delta_{\min} = 0.0010$ ($+0.10\%$ de ganancia de $R^2$), la media teórica bajo $H_1$ es:
$$\mathbb{E}[\bar{d}] = \delta_{\min} \times \mathrm{MSE}_{\mathrm{base}} \approx 0.0010 \times 10.58 = 0.01058$$

El error estándar de la pérdida diferencial depende de la dispersión de $d_t$. Definiendo el coeficiente de variación de las pérdidas relativas $\mathrm{CV}_d = \sigma_d / \mathbb{E}[d]$, se modela la potencia real para $N_{\mathrm{eff}} = 1\ 478.4$ observaciones independientes:

| Escenario de Dispersión Residual | $\sigma_d$ | $\mathrm{SE}(\bar{d})$ | Parámetro de No-Centralidad (NCP) | Potencia Estadística ($\alpha = 0.05$) | MDE al 80% de Potencia ($\Delta R^2$) |
|---|---:|---:|---:|---:|---:|
| **$\mathrm{CV} = 10$ (Baja dispersión)** | 0.1058 | 0.00275 | 3.84 | **98.6%** | $+0.065\%$ |
| **$\mathrm{CV} = 20$ (Dispersión moderada)** | 0.2116 | 0.00550 | 1.92 | **60.9%** | $+0.129\%$ |
| **$\mathrm{CV} = 30$ (Alta dispersión / colas pesadas)** | 0.3174 | 0.00825 | 1.28 | **35.8%** | $+0.194\%$ |
| **$\mathrm{CV} = 40$ (Dispersión extrema)** | 0.4232 | 0.01101 | 0.96 | **24.7%** | $+0.259\%$ |

> [!WARNING]
> **Rectificación y Veredicto de Potencia:**  
> La potencia estadística no puede declararse universalmente como "$>85\%$" sin condicionarla a la varianza del diferencial de pérdida $\sigma_d$.  
> - Si las observaciones atípicas no son sobreajustadas y $e_{\mathrm{alt}} \approx e_{\mathrm{base}}$, $d_t$ será pequeño en las colas ($\mathrm{CV} \le 15$), alcanzando potencias del $80\%\text{--}95\%$.
> - Si las colas generan oscilaciones en las predicciones ($\mathrm{CV} \ge 30$), la potencia para detectar exactamente $\delta_{\min} = 0.0010$ descenderá a $35\%\text{--}60\%$, elevando el efecto mínimo detectable detectable con solvencia a $\approx +0.15\%\text{--}+0.20\%$.  
> Por tanto, el número de observaciones limpias ($N = 13\ 558$) satisface con creces el umbral operativo preregistrado ($\ge 6\ 500$), pero la potencia real estará determinada por la estabilidad residual en las sesiones de baja volatilidad (S06 y S07).

---

### 6.3 Heterogeneidad y Regímenes de Mercado entre Sesiones

Las 7 sesiones capturadas no representan un régimen homogéneo, sino que abarcan condiciones disímiles de microestructura:

| Sesión | Obs. Válidas | Rango Horario (UTC) | Retorno Neto (bps) | Spread Medio (bps) | $\hat{\sigma}_{60}$ Media (bps) | Updates/s | $\mathrm{Kurt}(y)$ | Obs. con $|y|>10$ |
|:---:|---:|---|---:|---:|---:|---:|---:|---:|
| **01** | 2 259 | 16:58 – 17:38 | −4.77 | 0.0174 | 0.464 | 77.9 | 5.90 | 2 |
| **02** | 1 897 | 14:46 – 15:26 | −35.11 | 0.0156 | 0.586 | 96.9 | 1.79 | 0 |
| **03** | 1 286 | 15:26 – 16:06 | +12.72 | 0.0133 | 0.400 | 72.4 | 2.89 | 0 |
| **04** | 2 036 | 16:09 – 16:49 | +7.12 | 0.0153 | 0.435 | 77.9 | 5.75 | 0 |
| **05** | 2 194 | 16:54 – 17:34 | −4.84 | 0.0130 | 0.379 | 64.7 | 3.26 | 0 |
| **06** | 2 068 | 17:34 – 18:14 | −4.72 | 0.0126 | 0.309 | 54.2 | 203.14 | 17 |
| **07** | 1 818 | 18:14 – 18:54 | −17.65 | 0.0124 | 0.267 | 40.1 | 149.83 | 26 |

**Implicación para la inferencia OOS:**  
Las sesiones 1 a 5 representan regímenes de alta actividad y colas moderadas ($\mathrm{Kurt} \le 5.9$). Las sesiones 6 y 7 corresponden a regímenes crepusculares de menor liquidez y colas pesadas. La estabilidad de los coeficientes entre folds en el esquema walk-forward será una prueba de estrés fundamental para verificar si la geometría de liquidez es invariante al régimen.

---

## 7. Resultados de la Suite Automatizada de Pruebas

Ejecutado con: `pytest -v tests/test_dataset_v3.py tests/test_features_v3.py`

```
============================= test session starts =============================
platform win32 -- Python 3.10.9, pytest-8.4.2, pluggy-1.7.0 -- navier_lab_project\venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: navier_lab_project
plugins: platformdirs-4.12.4
collecting ... collected 19 items

tests/test_dataset_v3.py::test_research_dataset_v3_structure_and_hashes PASSED [  5%]
tests/test_dataset_v3.py::test_session_boundary_isolation PASSED         [ 10%]
tests/test_dataset_v3.py::test_features_causality_under_future_perturbations_v3 PASSED [ 15%]
tests/test_dataset_v3.py::test_target_horizon_and_normalization_protocol_adherence PASSED [ 21%]
tests/test_dataset_v3.py::test_gap_and_staleness_mask_propagation PASSED [ 26%]
tests/test_dataset_v3.py::test_compatibility_with_evaluate_models_oos_v3 PASSED [ 31%]
tests/test_dataset_v3.py::test_row_selection_and_masks_no_future_leakage PASSED [ 36%]
tests/test_dataset_v3.py::test_all_seven_sessions_raw_manifests_and_schemas PASSED [ 42%]
tests/test_features_v3.py::test_v3_features_presence_and_causality PASSED [ 47%]
tests/test_features_v3.py::test_v3_sign_and_contra_depth_selection PASSED [ 52%]
tests/test_features_v3.py::test_v3_pnpc_dimensionless_ratio PASSED       [ 57%]
tests/test_features_v3.py::test_target_gap_masking_comprehensive_boundaries PASSED [ 63%]
tests/test_features_v3.py::test_target_staleness_comprehensive_boundaries PASSED [ 68%]
tests/test_features_v3.py::test_streaming_equals_batch_comprehensive_v3 PASSED [ 73%]
tests/test_features_v3.py::test_v3_evaluation_common_sample_and_causal_scaling PASSED [ 78%]
tests/test_features_v3.py::test_v01_and_v02_invariance PASSED            [ 84%]
tests/test_features_v3.py::test_decision_matrix_resolution_of_conflicts PASSED [ 89%]
tests/test_features_v3.py::test_decision_matrix_deterministic_and_mece_exhaustive PASSED [ 94%]
tests/test_features_v3.py::test_bplusplus_dimensional_coherence PASSED   [100%]

============================= 19 passed in 16.04s =============================
```

La suite completa del repositorio (`pytest tests/`) reporta **48/48 pruebas aprobadas (100%)**.

---

## 8. Veredicto Final Rectificado de la Fase 4

| Criterio de Aceptación (Fase 4) | Estado | Evidencia y Justificación Cuantitativa |
|---|:---:|---|
| 1. Procesamiento independiente sin mezclar fronteras | **CUMPLIDO** | `test_session_boundary_isolation` aprobado; aislamiento verificado fila a fila. |
| 2. Hashes de archivos congelados intactos | **CUMPLIDO** | Coincidencia exacta (100%) con los manifiestos congelados. |
| 3. Dataset reconstruible de manera reproducible | **CUMPLIDO** | Script determinista [scripts/build_research_dataset_v3.py](file:///C:/Users/USER/Downloads/navier_lab_project/navier_lab_project/scripts/build_research_dataset_v3.py) produce hash `5e7139209...`. |
| 4. Causalidad, horizonte y máscaras verificadas | **CUMPLIDO** | Invarianza temporal demostrada ($t > t_0$ no afecta $t \le t_0$). |
| 5. Documentación de descartes, colinealidad y colas | **CUMPLIDO** | Partición jerárquica exacta de descartes (3 192), $\kappa(A) = 5.92$, censo de colas extremas ($N=45$) y potencia condicionada documentados. |
| 6. Compatibilidad con el motor OOS preregistrado | **CUMPLIDO** | Esquemas y funciones de preparación validadas sin errores ni nulos. |
| 7. Reporte literal de pruebas ejecutadas | **CUMPLIDO** | 48/48 pruebas aprobadas reportadas literalmente. |

### Veredicto: **`APROBADA CON LIMITACIONES DOCUMENTADAS`**

**Condiciones y advertencias preregistradas para la Fase 5:**
1. **Sensibilidad a colas pesadas:** Las 43 observaciones atípicas de las sesiones 6 y 7 no deben ser censuradas, pero su impacto en el MSE del Holdout debe ser analizado mediante la robustez del Bootstrap estacionario frente a Newey-West.
2. **Potencia condicionada a la dispersión:** Se reconoce que la potencia para detectar $+0.10\%$ en $R^2$ dependerá de la estabilidad de las pérdidas relativas ($\mathrm{CV}_d$), oscilando entre $35\%$ y $98\%$.
3. **Monotonía de rangos vs Alfa:** La correlación de Spearman $\rho \approx 0.90$ entre `v03_pnpc_k3` y los baselines exige que el contraste confirmatorio primario $C1$ (E vs B+++) sea el único árbitro del valor de la geometría.

---

## 9. Recomendación para la Siguiente Fase

1. **Detención inmediata confirmada:** No ejecutar modelos predictivos hasta la autorización formal de este informe ampliado.
2. **Paso siguiente una vez autorizada la Fase 5:** Proceder con la evaluación OOS preregistrada en [scripts/evaluate_models_oos_v3.py](file:///C:/Users/USER/Downloads/navier_lab_project/navier_lab_project/scripts/evaluate_models_oos_v3.py).
