# NAVIER V3 — Informe Metodológico Rectificado de Auditoría (v3_features_0.03)

**Documento:** `docs/v3_features_0.03.md`  
**Fecha:** 2026-10-24  
**Referencia de auditoría:** Evaluación crítica del informe [docs/v3_features_audit.md](file:///C:/Users/USER/Downloads/navier_lab_project/navier_lab_project/docs/v3_features_audit.md)  
**Dataset auditado:** [data/research_dataset_v3.parquet](file:///C:/Users/USER/Downloads/navier_lab_project/navier_lab_project/data/research_dataset_v3.parquet) (13 558 filas comunes, 51 columnas, SHA-256: `5e7139209...`)  
**Estado de la investigación:** FASE 4 AUDITADA Y CORREGIDA — FASE 5 (EVALUACIÓN OOS) BLOQUEADA  

---

> [!IMPORTANT]
> **Declaración de Integridad Científica y Preservación de Código:**  
> Ningún archivo congelado en la Fase 3 ([NAVIER_V3_PROTOCOL.md](file:///C:/Users/USER/Downloads/navier_lab_project/navier_lab_project/NAVIER_V3_PROTOCOL.md), [navier_lab/features.py](file:///C:/Users/USER/Downloads/navier_lab_project/navier_lab_project/navier_lab/features.py), [navier_lab/schema.py](file:///C:/Users/USER/Downloads/navier_lab_project/navier_lab_project/navier_lab/schema.py), [navier_lab/resampler.py](file:///C:/Users/USER/Downloads/navier_lab_project/navier_lab_project/navier_lab/resampler.py), [scripts/evaluate_models_oos_v3.py](file:///C:/Users/USER/Downloads/navier_lab_project/navier_lab_project/scripts/evaluate_models_oos_v3.py)) ha sido modificado.  
> Los datos no han sido filtrados ni alterados tras observar las colas. Este informe documenta y rectifica con exactitud matemática y evidencia empírica los errores de interpretación y asunciones analíticas cometidos en las versiones previas de la Fase 4.

---

## 1. Resumen de Errores y Desviaciones Analíticas Identificadas

| # | Área Crítica | Error o Aserción Excesiva Identificada | Causa Raíz / Diagnóstico Técnico | Acción Requerida |
|---|---|---|---|---|
| **1** | **Potencia Estadística** | La tabla de potencia reportada correspondía a un contraste **unilateral** al 5%, mientras que el protocolo exige un contraste **bilateral**. | En `power_sim.py` se utilizó $z_{\mathrm{crit}} = 1.6449$ ($\alpha = 0.05$ unilateral). Sin embargo, [scripts/evaluate_models_oos_v3.py#L210](file:///C:/Users/USER/Downloads/navier_lab_project/navier_lab_project/scripts/evaluate_models_oos_v3.py#L210) calcula `2.0 * stats.norm.sf(abs(t))`, que es estrictamente **bilateral** ($z_{\mathrm{crit}} = 1.95996$). | Rectificar la tabla de potencia al contraste bilateral y explicitar la pérdida de potencia en escenarios de alta dispersión. |
| **2** | **Inferencia Newey–West** | Se concluyó que $L=20$ «captura la totalidad de la dependencia $\mathrm{MA}(9)$». | La $\mathrm{LRV}$ aumenta un $+6.25\%$ entre $L=20$ y $L=40$. Además, se evaluó $y^2$ y no el diferencial de pérdidas real $d_t = e_{\mathrm{base}}^2 - e_{\mathrm{alt}}^2$. | Matizar la conclusión: $L=20$ es el valor primario preregistrado ($2H$), mientras que $L=10$ y $L=40$ son análisis de sensibilidad; el Bootstrap por bloques es la salvaguarda no paramétrica. |
| **3** | **Régimen de Mercado** | Se calificó a las Sesiones 06 y 07 como de «menor liquidez». | En las Sesiones 06 y 07 el spread medio fue **menor** ($0.0124$ bps vs $0.0174$ bps en S01) y la profundidad fue **mayor** ($13.77$ BTC vs $12.86$ BTC en S02). Menos actualizaciones no implica menor liquidez. | Reemplazar por la descripción empírica rigurosa: *«régimen de baja actividad de actualización y baja volatilidad estimada»*. |
| **4** | **Observaciones Extremas** | Se asumió que las 45 observaciones con $|y|>10$ eran independientes. | Debido al solapamiento del horizonte $H=10$ s, observaciones consecutivas comparten la misma trayectoria de precio. Las 45 filas corresponden en realidad a solo **7 episodios de mercado**. | Censar los 7 clusters temporales y mapear su distribución asimétrica en los folds de evaluación (0 en Splits 1–3, 13 en Split 4, 30 en Holdout). |
| **5** | **Condicionamiento Matricial** | Se afirmó que el bajo número de condición garantiza la robustez del modelo. | $\kappa(A^\top A) \approx 35.06$ garantiza estabilidad en la inversión numérica del álgebra lineal, pero no estabilidad predictiva fuera de muestra ni descarta la redundancia con $\mathrm{OFI}$ ($\rho = 0.9002$). | Delimitar la conclusión al cálculo numérico y reiterar que la prueba definitiva es el contraste OOS preregistrado $C1$. |

---

## 2. Rectificación de la Potencia Estadística: Contraste Bilateral vs. Unilateral

### 2.1 Especificación Exacta en el Código Congelado

En el motor de evaluación congelado [scripts/evaluate_models_oos_v3.py](file:///C:/Users/USER/Downloads/navier_lab_project/navier_lab_project/scripts/evaluate_models_oos_v3.py), la función `diebold_mariano_test` implementa:

```python
# scripts/evaluate_models_oos_v3.py, línea 209-210:
t_stat = dm_mean / se
p_val = float(2.0 * stats.norm.sf(abs(t_stat)))
```

La multiplicación por `2.0` sobre la función de supervivencia del valor absoluto define inequívocamente un **contraste bilateral** con nivel de significancia nominal $\alpha = 0.05$, cuyo valor crítico en la distribución normal estándar es:
$$z_{1 - \alpha/2} = \Phi^{-1}(0.975) \approx \mathbf{1.95996}$$

En el informe previo, se empleó erróneamente el cuantil unilateral $z_{1-\alpha} = \Phi^{-1}(0.95) \approx \mathbf{1.64485}$.

---

### 2.2 Comparación Matemática de Potencia y Parámetro de No-Centralidad

Bajo la hipótesis alternativa $H_1$, con una mejora teórica igual al umbral de futilidad preregistrado $\delta_{\min} = 0.0010$ ($+0.10\%$ en $R^2_{\mathrm{OOS}}$):
$$\mathbb{E}[\bar{d}] = \delta_{\min} \times \mathrm{MSE}_{\mathrm{base}} \approx 0.0010 \times 10.5803 = 0.010580$$

Para un tamaño muestral efectivo $N_{\mathrm{eff}} = 1\ 478.4$ observaciones independientes, el error estándar del diferencial de pérdidas es:
$$\mathrm{SE}(\bar{d}) = \frac{\sigma_d}{\sqrt{N_{\mathrm{eff}}}}$$

El parámetro de no-centralidad es $\lambda = \frac{\mathbb{E}[\bar{d}]}{\mathrm{SE}(\bar{d})} = \frac{0.01058}{\sigma_d / \sqrt{1478.4}} = \frac{\sqrt{1478.4}}{\mathrm{CV}_d} \approx \frac{38.45}{\mathrm{CV}_d}$, donde $\mathrm{CV}_d = \frac{\sigma_d}{\mathbb{E}[\bar{d}]}$.

La potencia estadística se define respectivamente como:
- **Unilateral ($\alpha = 0.05$):** $1 - \Phi(1.6449 - \lambda)$.
- **Bilateral ($\alpha = 0.05$):** $1 - \Phi(1.9600 - \lambda) + \Phi(-1.9600 - \lambda) \approx 1 - \Phi(1.9600 - \lambda)$.

#### Tabla Comparativa de Potencia:

| Coeficiente de Variación ($\mathrm{CV}_d$) | Desv. Est. $\sigma_d$ | Error Estándar $\mathrm{SE}(\bar{d})$ | Parámetro $\lambda$ (NCP) | Potencia Unilateral (Reportada Previamente) | **Potencia Bilateral Exacta (Protocolo)** | Disminución de Potencia |
|:---:|---:|---:|---:|---:|---:|---:|
| **10** | 0.1058 | 0.00275 | 3.845 | 98.6% | **96.99% ($\approx 97.0\%$)** | −1.6% |
| **20** | 0.2116 | 0.00550 | 1.922 | 60.9% | **48.49% ($\approx 48.5\%$)** | −12.4% |
| **30** | 0.3174 | 0.00825 | 1.282 | 35.8% | **24.88% ($\approx 25.0\%$)** | −10.9% |
| **40** | 0.4232 | 0.01101 | 0.961 | 24.7% | **15.89% ($\approx 16.3\%$)** | −8.8% |
| **50** | 0.5290 | 0.01376 | 0.769 | 19.1% | **11.69% ($\approx 11.7\%$)** | −7.4% |

$$\begin{aligned}
\text{Para } \mathrm{CV} = 20: \quad &\text{Potencia}_{\text{bilateral}} = 1 - \Phi(1.9600 - 1.9224) = 1 - \Phi(0.0376) = 1 - 0.5150 = \mathbf{48.5\%}. \\
\text{Para } \mathrm{CV} = 30: \quad &\text{Potencia}_{\text{bilateral}} = 1 - \Phi(1.9600 - 1.2816) = 1 - \Phi(0.6784) = 1 - 0.7512 = \mathbf{24.9\%}.
\end{aligned}$$

### Consecuencia Metodológica:
La potencia para detectar un efecto de futilidad en el contraste confirmatorio $C1$ **no es del $85\%$ a priori**. Si la dispersión de las pérdidas relativas es moderada o alta ($\mathrm{CV}_d \ge 20$), la probabilidad de detectar una mejora de $\Delta R^2 = +0.10\%$ se sitúa entre el $25\%$ y el $48\%$. Para alcanzar una potencia del $80\%$ bajo un contraste bilateral con $\mathrm{CV}_d = 20$, el **efecto mínimo detectable (MDE)** asciende a:
$$\mathrm{MDE}_{80\%} = (z_{0.975} + z_{0.80}) \times \frac{\mathrm{SE}(\bar{d})}{\mathrm{MSE}_{\mathrm{base}}} = (1.960 + 0.842) \times \frac{0.00550}{10.58} = \mathbf{+0.146\% \text{ de } R^2_{\mathrm{OOS}}}.$$

---

## 3. Matización de Newey–West: Dependencia de $y^2$ vs. Diferencial de Pérdidas $d_t$

En el informe previo se afirmó que «$L=20$ captura la totalidad de la estructura de solapamiento $\mathrm{MA}(9)$». Esta aserción es metodológicamente excesiva por dos razones técnicas:

1. **Sensibilidad Residual No Nula en la LRV:**
   Al duplicar el ancho de banda de $L=20$ a $L=40$, la estimación de varianza de largo plazo sobre $y^2$ pasa de $282\ 642$ a $300\ 312$:
   $$\Delta \mathrm{LRV} = \frac{300\ 312 - 282\ 642}{282\ 642} = \mathbf{+6.25\%}.$$
   Un incremento del $6.25\%$ no refuta la utilidad de $L=20$, pero sí demuestra que existe persistencia residual en rezagos altos que el estimador con núcleo de Bartlett no agota por completo.
2. **Divergencia entre $y^2$ y $d_t$:**
   Se calculó la $\mathrm{LRV}$ sobre la serie $y_t^2$ (pérdida cuadrática de un predictor nulo). Sin embargo, la prueba Diebold-Mariano evalúa:
   $$d_t = e_{\mathrm{base},t}^2 - e_{\mathrm{alt},t}^2 = 2 e_t \Delta \hat{y}_t - (\Delta \hat{y}_t)^2.$$
   La estructura temporal de $d_t$ depende de la covarianza cruzada entre los residuos $e_t$ y las predicciones incrementales $\Delta \hat{y}_t$. Puede ser menos persistente que $y_t^2$ si los errores se blanquean tras el ajuste, o más heterocedástica si las predicciones reaccionan a regímenes de volatilidad.

### Directriz para la Fase 5:
- **$L=20$ lags ($2H$)** se conserva como el parámetro primario indiscutible del protocolo preregistrado ([NAVIER_V3_PROTOCOL.md#L239](file:///C:/Users/USER/Downloads/navier_lab_project/navier_lab_project/NAVIER_V3_PROTOCOL.md#L239)).
- **$L=10$ y $L=40$** deben interpretarse estrictamente como **análisis de sensibilidad**.
- La salvaguarda confirmatoria frente a la distorsión asintótica de Newey-West en presencia de colas pesadas es el **Stationary Block Bootstrap** ($B = 1000$, $1/p = 15$ s), el cual remuestrea bloques temporales completos sin depender de la convergencia del estimador $\mathrm{HAC}$.

---

## 4. Corrección de Régimen de Mercado: «Baja Actividad y Volatilidad Estimada», No «Menor Liquidez»

En el informe previo se describió a las Sesiones 06 y 07 como de «menor liquidez» basándose en la reducción del conteo de mensajes de actualización. Esta afirmación es empíricamente incorrecta y confunde **actividad transaccional** con **liquidez de libro**:

### Evidencia Empírica de Microestructura por Sesión:

| Sesión | Updates/s | Volatilidad Media $\hat{\sigma}_{60}$ | **Spread Medio (bps)** | **Spread p95 (bps)** | **Profundidad Media L2 (BTC)** | Retorno Neto (bps) |
|:---:|---:|---:|---:|---:|---:|---:|
| **01** | 77.9 | 0.464 bps | 0.0174 bps | 0.0123 bps | 13.83 BTC | −4.77 |
| **02** | 96.9 | 0.586 bps | 0.0156 bps | 0.0123 bps | 12.86 BTC | −35.11 |
| **03** | 72.4 | 0.400 bps | 0.0133 bps | 0.0123 bps | 12.69 BTC | +12.72 |
| **04** | 77.9 | 0.435 bps | 0.0153 bps | 0.0123 bps | 13.19 BTC | +7.12 |
| **05** | 64.7 | 0.379 bps | 0.0130 bps | 0.0123 bps | 13.54 BTC | −4.84 |
| **06** | **54.2** | **0.309 bps** | **0.0126 bps** | **0.0123 bps** | **13.13 BTC** | −4.72 |
| **07** | **40.1** | **0.267 bps** | **0.0124 bps** | **0.0123 bps** | **13.77 BTC** | −17.65 |

### Diagnóstico:
1. El spread medio en la Sesión 07 ($0.0124$ bps) fue el **más estrecho de todo el dataset de validación**, un $28.7\%$ más ajustado que en la Sesión 01 ($0.0174$ bps).
2. La profundidad acumulada de 10 niveles en la Sesión 07 ($13.77$ BTC) fue superior a la de las Sesiones 02, 03 y 04.
3. Lo que ocurrió entre las 17:34 y las 18:54 UTC fue una **desaceleración de la llegada de órdenes** (menos cancelaciones y reposiciones por segundo) acompañada de una **compresión de la volatilidad realizada**. El libro permaneció denso y con horquilla mínima.

**Definición corregida:**  
Se adopta en toda la documentación la denominación técnica exacta:  
**«Régimen de baja actividad de actualización y baja volatilidad estimada»**.

---

## 5. Agrupamiento Temporal de Extremos: 45 Observaciones Representan 7 Episodios de Mercado

### 5.1 Censo de Clusters por Solapamiento de Horizonte

El target mide retornos a 10 segundos: $y(t) = \frac{\ln(\mathrm{mid}(t+10)/\mathrm{mid}(t)) \times 10^4}{\hat{\sigma}_{60}(t) \sqrt{10}}$.  
Si ocurre un movimiento de precio en un intervalo de reposo, cada segundo consecutivo en que ese movimiento queda contenido dentro de la ventana de 10 segundos produce un valor de $y$ atípico.

Al analizar las 45 observaciones con $|y| > 10.0$ agrupando filas consecutivas con distancia temporal $\le 10$ s, se descubre que **provienen de exactamente 7 episodios físicos de mercado**:

| Episodio (Cluster) | Sesión | Filas en Cluster | Duración Temporal | Timestamp Inicio (UTC) | Timestamp Fin (UTC) | Rango de $y$ | Retorno $y_{\mathrm{bps}}$ | $\hat{\sigma}_{60}$ Medio |
|:---:|:---:|---:|---:|---|---|---:|---:|---:|
| **1** | **S01** | 2 | 2 s | `2026-10-22 17:15:04` | `2026-10-22 17:15:05` | $[+10.86, +11.07]$ | +6.44 bps | 0.1857 bps |
| **2** | **S06** | 3 | 3 s | `2026-10-23 17:46:20` | `2026-10-23 17:46:22` | $[+10.53, +10.53]$ | +2.83 bps | 0.0851 bps |
| **3** | **S06** | 10 | 10 s | `2026-10-23 17:52:06` | `2026-10-23 17:52:15` | $[-91.49, -43.80]$ | −4.99 bps | 0.0305 bps |
| **4** | **S06** | 4 | 4 s | `2026-10-23 18:03:20` | `2026-10-23 18:03:23` | $[-14.46, -10.66]$ | −3.28 bps | 0.0780 bps |
| **5** | **S07** | 9 | 9 s | `2026-10-23 18:20:58` | `2026-10-23 18:21:06` | $[-21.32, -10.38]$ | −1.82 bps | 0.0459 bps |
| **6** | **S07** | 10 | 10 s | `2026-10-23 18:40:48` | `2026-10-23 18:40:57` | $[+48.48, +94.89]$ | +2.35 bps | 0.0113 bps |
| **7** | **S07** | 7 | 7 s | `2026-10-23 18:46:03` | `2026-10-23 18:46:09` | $[-107.21, -20.19]$ | −3.29 bps | 0.0323 bps |

$$\sum \text{Filas de los 7 Clusters} = 2 + 3 + 10 + 4 + 9 + 10 + 7 = \mathbf{45} \text{ observaciones}.$$

---

### 5.2 Distribución Asimétrica en las Particiones del Motor de Evaluación

Se examinaron las fronteras exactas calculadas por `make_walk_forward_splits` y el holdout del $20\%$ en [scripts/evaluate_models_oos_v3.py](file:///C:/Users/USER/Downloads/navier_lab_project/navier_lab_project/scripts/evaluate_models_oos_v3.py#L150-L164):
- **Conjunto de Evaluación (Walk-Forward 80%):** Filas `0` a `10 845` ($10\ 846$ filas, desde `16:59:53 UTC día 1` hasta `17:57:41 UTC día 2`).
- **Conjunto de Holdout (20% final):** Filas `10 846` a `13 557` ($2\ 712$ filas, desde `17:57:42 UTC` hasta `18:54:35 UTC día 2`).

```
Distribución de las 45 observaciones extremas en el esquema experimental:
  - Walk-Forward Test Split 1:   0 observaciones (|y| > 10)
  - Walk-Forward Test Split 2:   0 observaciones (|y| > 10)
  - Walk-Forward Test Split 3:   0 observaciones (|y| > 10)
  - Walk-Forward Test Split 4:  13 observaciones (|y| > 10)  <- Episodios 2 y 3 (Sesión 06)
  ------------------------------------------------------------------------------------------
  - Holdout Final (20% OOS):    30 observaciones (|y| > 10)  <- Episodios 4, 5, 6 y 7 (Sesiones 06 y 07)
```

### Implicaciones Críticas para la Fase 5:
1. **Splits 1, 2 y 3 están completamente limpios de observaciones con $|y| > 10$:**  
   Esto constituye una ventaja metodológica para el protocolo. La regla de consistencia del walk-forward (§8.3) exige al menos 3 de 4 folds positivos ($\ge 75\%$). Si el Modelo E tuviera una ventaja espuria derivada de sobreajustar estos 7 episodios, fracasaría en los Splits 1, 2 y 3.
2. **Validación del Stationary Block Bootstrap:**  
   Los clusters duran entre 2 y 10 segundos. El bootstrap de bloques geométricos preregistrado con longitud media $1/p = 15$ s engloba los episodios enteros dentro de un mismo bloque, preservando la dependencia serial de los residuos sin tratarlos erróneamente como eventos independientes.

---

## 6. Interpretación del Condicionamiento de la Matriz

El informe previo reportó:
- $\mathrm{Cond}(A) = 5.92$
- $\mathrm{Cond}(A^\top A) = 35.06 \approx 5.92^2$
- Autovalor mínimo con Ridge ($\lambda = 10^{-6} N$): $\lambda_{\min} = 1\ 816.94$

### Clarificación Metodológica:
1. **Estabilidad aritmética vs. Estabilidad OOS:**  
   Estos números confirman que el algoritmo de resolución numérica `np.linalg.solve(A.T @ A + ridge_eye, A.T @ y)` no sufre cancelación catastrófica ni errores de redondeo en punto flotante (`float64`).
2. **No inmunidad frente a redundancia:**  
   Que una matriz esté bien condicionada aritméticamente **no implica** que los nuevos predictores contengan información predictiva incremental.  
   Dado que `v03_pnpc_k3` tiene una correlación de Spearman de $+0.9037$ con la penetración convencional `_ofi_div_depth10` y de $+0.9002$ con `ofi_5`, los coeficientes de regresión podrían sufrir absorción o inestabilidad muestral si la señal está duplicada.  
3. **El veredicto final corresponde a $C1$:**  
   La prueba confirmatoria preregistrada **$C1$ (Modelo E vs Modelo B+++)** es la única instancia que determinará si la concentración geométrica y la modulación por libro contrario aportan reducción real del error de predicción.

---

## 7. ¿Hay que Modificar Algo en el Dataset o en el Código?

### Veredicto de Preservación: **NO MODIFICAR NADA EN EL CÓDIGO NI EN LOS DATOS CONGELADOS**

1. **Inviolabilidad de las Capturas y el Dataset:**  
   Las 13 558 observaciones de [data/research_dataset_v3.parquet](file:///C:/Users/USER/Downloads/navier_lab_project/navier_lab_project/data/research_dataset_v3.parquet) son legítimas y reproducibles. Censurar las observaciones extremas o cambiar el suelo de volatilidad $\sigma_{60} \ge 0.01$ bps tras haber inspeccionado los datos constituiría una manipulación post-hoc (*p-hacking* / sesgo de selección) prohibida por la Sección 11 del protocolo.
2. **Inviolabilidad de los Scripts Congelados:**  
   El motor de evaluación [scripts/evaluate_models_oos_v3.py](file:///C:/Users/USER/Downloads/navier_lab_project/navier_lab_project/scripts/evaluate_models_oos_v3.py) ya cuenta con los mecanismos preestablecidos para gestionar estas limitaciones:
   - Recorte causal `clip_sd = 5.0` en los predictores.
   - Regularización Ridge mínima $\lambda = 10^{-6} N$.
   - Contraste bilateral explícito en `diebold_mariano_test`.
   - Reporte de sensibilidad de rezagos Newey-West en $L=10$ y $L=40$.
   - Intervalos de confianza por Stationary Block Bootstrap ($B = 1000$).
   - Regla de consistencia multifold ($\ge 3/4$ folds positivos) que neutraliza la influencia aislada del Split 4.
3. **Alcance de las Modificaciones:**  
   Las modificaciones se limitan exclusivamente al plano de la **auditoría, la documentación y la calibración de expectativas de potencia**, tal como quedan registradas en este documento y en [docs/v3_features_audit.md](file:///C:/Users/USER/Downloads/navier_lab_project/navier_lab_project/docs/v3_features_audit.md).

---

## 8. Veredicto Final de la Fase 4

### **`APROBADA CON LIMITACIONES FORMALMENTE DOCUMENTADAS`**

El dataset cumple con todos los requisitos de integridad causal, ausencia de fugas temporales, aislamiento de sesiones y reproducibilidad criptográfica. La Fase 4 queda cerrada con un conocimiento cuantitativo exacto de los 7 clusters de colas pesadas, el condicionamiento matricial y la potencia real del contraste bilateral.

**Siguiente paso:** Esperar la autorización formal para ejecutar la Fase 5:
```powershell
python scripts/evaluate_models_oos_v3.py --dataset data/research_dataset_v3.parquet --output results/oos_model_evaluation_v3.json
```
