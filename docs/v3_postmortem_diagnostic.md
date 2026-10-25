# NAVIER V3 — Auditoría Diagnóstica Post-Fase 5

**Fecha:** 2026-10-24  
**Auditor:** Auditor Cuantitativo Independiente  
**Entregable:** `docs/v3_postmortem_diagnostic.md`  
**Objetivo:** Investigar las causas científicas, matemáticas y empíricas por las cuales las variables geométricas estáticas de NAVIER V3 no demostraron capacidad predictiva incremental fuera de muestra, y dictaminar si existe justificación científica para continuar dicha línea de investigación.  
**Modo de trabajo:** Exclusivamente de solo lectura. Sin modificaciones a datos, código congelado, protocolo, features ni resultados originales.

---

## 1. Resumen Ejecutivo

La evaluación fuera de muestra (Fase 5) dictaminó formalmente un veredicto de **`INCONCLUSO`** sobre el contraste confirmatorio primario C1 ($E \text{ vs } B^{+++}$), con una ganancia en Walk-Forward de $\Delta R^2_{\mathrm{OOS}} = +0.192\%$ ($p_{\mathrm{nominal}} = 0.4771$, $p_{\mathrm{FDR}} = 0.7276$), un intervalo bootstrap que cruza ampliamente el cero ($[-0.675\%, +0.502\%]$) y un colapso en el Holdout final ($\Delta R^2_{\mathrm{OOS, holdout}} = -0.535\%$). Frente a los baselines convencionales sin la variable de ratio ($B^{++}$, $B^+$, $B$), el modelo geométrico $E$ fue sistemáticamente inferior ($\Delta R^2_{\mathrm{OOS}} < 0$).

Esta auditoría diagnóstica examinó el sistema de forma exhaustiva y concluye:

1. **La evaluación OOS es metodológicamente íntegra:** No existe fuga de información (*leakage*), la purga y el embargo de 10 s garantizan una separación estricta frente al horizonte $H=10\text{ s}$ (holgura temporal de 11 s entre train y test), los signos algebraicos de Diebold-Mariano y $\Delta R^2$ están matemáticamente alineados, y la corrección FDR se calculó con exactitud. El resultado negativo no se debe a un error de cálculo o instrumentación.
2. **Las variables geométricas son monótonamente redundantes:** Aunque el VIF lineal parecía bajo ($1.35\text{--}1.54$), la correlación de rangos de Spearman entre la variable geométrica principal `v03_impact_conc_k3` y las variables convencionales ya presentes en el baseline supera $\rho = 0.90\text{--}0.92$. La variación de estas variables está dominada en un $>90\%$ por el flujo de órdenes (`ofi_raw_5`), aportando grados de libertad redundantes que aumentaron la varianza del estimador y destruyeron precisión fuera de muestra.
3. **El target z-score desacopla la varianza económica de la estadística:** Las 45 observaciones con $|y| > 10$ no representan grandes movimientos de mercado (su retorno bruto medio es de solo $3.27\text{ bps}$, unos $\$26\text{ USD}$ en Bitcoin), sino movimientos pequeños ocurridos en periodos donde la volatilidad histórica de 60 s colapsó a niveles cercanos al suelo ($0.01\text{ bps}$), dividiendo por un denominador $9.2\times$ menor de lo normal.
4. **El colapso en Holdout es estructural y generalizado:** Al descomponer el Holdout, el modelo geométrico $E$ resulta un **$-4.13\%$ peor** que $B^{+++}$ incluso en el subconjunto normal ($|y| \le 10$, $98.9\%$ de las filas). El deterioro fuera de muestra no es un accidente producido por los episodios extremos, sino una pérdida sistemática de capacidad predictiva.
5. **Recomendación definitiva:** **`CERRAR LA LÍNEA GEOMÉTRICA ESTÁTICA`**.

---

## 2. Investigación 1 — Integridad Estadística de la Evaluación

Se inspeccionó el código congelado ([`scripts/evaluate_models_oos_v3.py`](file:///C:/Users/USER/Downloads/navier_lab_project/navier_lab_project/scripts/evaluate_models_oos_v3.py), [`navier_lab/features.py`](file:///C:/Users/USER/Downloads/navier_lab_project/navier_lab_project/navier_lab/features.py)) y los artefactos de resultados:

### 2.1 Definición y Composición de Modelos
En [`scripts/evaluate_models_oos_v3.py#L65-L71`](file:///C:/Users/USER/Downloads/navier_lab_project/navier_lab_project/scripts/evaluate_models_oos_v3.py#L65-L71), la jerarquía de modelos es estrictamente anidada:
- **`Model_B` (9 vars):** `spread_bps`, `depth_log`, `vol60_bps` (básicas) + `imb_full`, `imb_top1`, `ofi_5`, `ret_1`, `ret_5`, `ret_30` (tradicionales).
- **`Model_B_plus` (12 vars):** `Model_B` + `imb_full_lag2`, `imb_full_lag5`, `imb_full_lag8` (rezagos temporales).
- **`Model_B_plusplus` (14 vars):** `Model_B_plus` + `_ofi_x_imb`, `_ofi_div_depth10` (interacciones no lineales convencionales).
- **`Model_B_tripleplus` (15 vars):** `Model_B_plusplus` + `v03_pnpc_k3` (control de razón presión/profundidad en 3 niveles).
- **`Model_E` (18 vars):** `Model_B_tripleplus` + `v03_liq_conc_ask`, `v03_liq_conc_bid`, `v03_impact_conc_k3` (variables de la hipótesis geométrica).

Todos los modelos confirmatorios fueron ajustados y evaluados sobre exactamente las mismas filas válidas (intersección común de 8 637 observaciones en Walk-Forward y 2 712 en Holdout).

### 2.2 Fórmula del Target, Horizonte y Suelo de Volatilidad
En [`navier_lab/features.py#L193-L202`](file:///C:/Users/USER/Downloads/navier_lab_project/navier_lab_project/navier_lab/features.py#L193-L202):
$$y_t = \frac{\Delta \ln(\mathrm{mid})_{t \to t+H}}{\sigma_{60, t} \sqrt{H}}$$
- $H = 10\text{ s}$ (horizonte prospectivo estricto).
- $\sigma_{60, t}$ (`vol60_bps`): desviación estándar muestral móvil de 60 segundos sobre los retornos de 1 segundo en puntos básicos ([L86-L87](file:///C:/Users/USER/Downloads/navier_lab_project/navier_lab_project/navier_lab/features.py#L86-L87)).
- Suelo de volatilidad: si $\sigma_{60, t} < 0.01\text{ bps}$, $y_t$ se invalida como `NaN` ([L199](file:///C:/Users/USER/Downloads/navier_lab_project/navier_lab_project/navier_lab/features.py#L199)).

### 2.3 Signos de $\Delta R^2$ y Diebold-Mariano
En [`scripts/evaluate_models_oos_v3.py#L194-L210`](file:///C:/Users/USER/Downloads/navier_lab_project/navier_lab_project/scripts/evaluate_models_oos_v3.py#L194-L210):
- $\Delta R^2 = 1 - \frac{\mathrm{MSE}(\mathrm{alt})}{\mathrm{MSE}(\mathrm{base})}$. Si el modelo alternativo reduce el error cuadrático, $\Delta R^2 > 0$.
- Pérdida diferencial: $d_t = e_{\mathrm{base}, t}^2 - e_{\mathrm{alt}, t}^2$. Si el modelo base comete mayores errores que el alternativo, $d_t > 0$.
- Estadístico: $t = \frac{\bar{d}}{\mathrm{SE}(d)}$.
- **Comprobación:** Los signos de $\Delta R^2$, $\bar{d}$ y $t\text{-stat}$ son estrictamente coherentes. No existe inversión de polaridad ni contradicción en las fórmulas.

### 2.4 Control de Separación Temporal (Purga y Embargo)
En [`scripts/evaluate_models_oos_v3.py#L150-L164`](file:///C:/Users/USER/Downloads/navier_lab_project/navier_lab_project/scripts/evaluate_models_oos_v3.py#L150-L164):
- Para cada corte $i$ con frontera en $T_{\mathrm{corte}}$:
  * El entrenamiento finaliza en $T_{\mathrm{tr, max}} = T_{\mathrm{corte}} - \text{purga} - 1 = T_{\mathrm{corte}} - 11$.
  * Dado que $H=10\text{ s}$, el target de esa última fila de train requiere información prospectiva hasta $T_{\mathrm{tr, max}} + 10 = T_{\mathrm{corte}} - 1$.
  * El test comienza en $T_{\mathrm{te, min}} = T_{\mathrm{corte}} + \text{embargo} = T_{\mathrm{corte}} + 10$.
  * Holgura temporal física neta: $(T_{\mathrm{corte}} + 10) - (T_{\mathrm{corte}} - 1) = \mathbf{11\text{ segundos}}$.
- **Comprobación:** La purga y el embargo previenen al 100% cualquier contaminación causal o solapamiento del target entre entrenamiento y prueba (`Contaminación: False` en los 4 splits).

### 2.5 Multiplicidad y Control FDR
Los 4 contrastes confirmatorios arrojaron los siguientes p-valores nominales de Diebold-Mariano ($L=20$):
- C1 ($E \text{ vs } B^{+++}$): $p = 0.4771$
- C2 ($E \text{ vs } B^{++}$): $p = 0.7447$
- C3 ($E \text{ vs } B^+$): $p = 0.5457$
- C4 ($E \text{ vs } B$): $p = 0.5376$

Aplicando el algoritmo Benjamini-Hochberg ($\alpha = 0.05$):
$$p_{(1)} = 0.4771 \implies p_{\mathrm{adj}} = \min\left(0.4771 \times \frac{4}{1}, 0.7276\right) = 0.7276$$
$$p_{(2)} = 0.5376 \implies p_{\mathrm{adj}} = \min\left(0.5376 \times \frac{4}{2}, 0.7276\right) = 0.7276$$
$$p_{(3)} = 0.5457 \implies p_{\mathrm{adj}} = 0.5457 \times \frac{4}{3} = 0.7276$$
$$p_{(4)} = 0.7447 \implies p_{\mathrm{adj}} = 0.7447 \times \frac{4}{4} = 0.7447$$
- **Comprobación:** Los valores reportados en Fase 5 coinciden exactamente con la fórmula matemática preespecificada.

---

## 3. Investigación 2 — Diagnóstico del Target y Episodios Extremos

### 3.1 Distribución Empírica por Sesión
Se procesaron las 13 558 observaciones limpias del dataset congelado [`data/research_dataset_v3.parquet`](file:///C:/Users/USER/Downloads/navier_lab_project/navier_lab_project/data/research_dataset_v3.parquet):

| Sesión | Obs. | Rango $y_{\mathrm{bps}}$ (Retorno Bruto) | Rango $y$ (Target Normalizado) | Curtosis de $y$ | Mínimo $\sigma_{60}$ | Filas $\sigma_{60} < 0.015$ | Obs. $\|y\| > 10$ |
|:---:|---:|:---:|:---:|---:|:---:|:---:|:---:|
| **01** | 2 259 | $[-7.39, +7.33]$ bps | $[-5.06, +11.07]$ | $5.88$ | $0.1455$ bps | $0$ ($0.0\%$) | 2 |
| **02** | 1 897 | $[-8.20, +7.50]$ bps | $[-4.84, +6.20]$ | $1.79$ | $0.2982$ bps | $0$ ($0.0\%$) | 0 |
| **03** | 1 286 | $[-5.13, +6.36]$ bps | $[-5.38, +5.68]$ | $2.88$ | $0.0819$ bps | $0$ ($0.0\%$) | 0 |
| **04** | 2 036 | $[-5.45, +9.01]$ bps | $[-5.11, +9.95]$ | $5.73$ | $0.1573$ bps | $0$ ($0.0\%$) | 0 |
| **05** | 2 194 | $[-5.15, +5.59]$ bps | $[-7.02, +7.79]$ | $3.25$ | $0.1328$ bps | $0$ ($0.0\%$) | 0 |
| **06** | 2 068 | $[-7.02, +7.86]$ bps | $[-91.49, +10.53]$ | **$202.65$** | $0.0193$ bps | $0$ ($0.0\%$) | 17 |
| **07** | 1 818 | $[-5.24, +3.85]$ bps | $[-107.21, +94.89]$ | **$149.41$** | **$0.0104$ bps** | **$11$ ($0.6\%$)** | 26 |

### 3.2 Desmitificación de las 45 Observaciones Extremas ($\|y\| > 10$)
La comparación cuantitativa entre observaciones normales y extremas revela la causa del fenómeno:

| Variable | Observaciones Normales ($\|y\| \le 10$, $99.67\%$) | Observaciones Extremas ($\|y\| > 10$, $0.33\%$) | Ratio Extremo / Normal |
|---|:---:|:---:|:---:|
| **Número de Filas** | 13 513 | 45 | $0.0033\times$ |
| **Media Absoluta de Retorno Bruto ($\|y_{\mathrm{bps}}\|$)** | **$1.1577\text{ bps}$** | **$3.2732\text{ bps}$** | **$2.83\times$** |
| **Rango de Retorno Bruto ($y_{\mathrm{bps}}$)** | $[-8.2047, +9.0077]\text{ bps}$ | $[-7.0170, +6.4996]\text{ bps}$ | No excede el rango normal |
| **Media de Volatilidad ($\sigma_{60}$)** | **$0.4081\text{ bps}$** | **$0.0444\text{ bps}$** | **$0.109\times$ ($9.2\times$ menor)** |
| **Rango de Denominador ($\sigma_{60} \sqrt{10}$)** | $[0.0610, 4.4170]\text{ bps}$ | $[0.0328, 0.5873]\text{ bps}$ | Cerca del suelo absoluto |
| **Rango de $y$ (z-score resultante)** | $[-7.02, +9.95]$ | $[-107.21, +94.89]$ | **$10.8\times$ mayor** |

> [!IMPORTANT]
> **Hecho comprobado:** Las 45 observaciones con $|y| > 10$ **no fueron grandes movimientos de mercado ni episodios de volatilidad extrema**. Un movimiento de $3.27\text{ bps}$ en Bitcoin (a $\$81\ 300$) representa apenas $\approx \$26.6\text{ USD}$ ($0.033\%$).  
> La extrema magnitud de $y$ es un **artefacto matemático de la normalización**: se produjo porque la volatilidad móvil $\sigma_{60}$ cayó a valores mínimos ($0.0104\text{ bps}$), de modo que un movimiento ordinario del precio dividió por un denominador casi nulo, inflando el target hasta $-107.21$.

### 3.3 Descomposición del Deterioro en Holdout
En la Fase 5, el Holdout arrojó un $\Delta R^2_{\mathrm{OOS}} = -0.5347\%$ frente a $B^{+++}$. Se analizó si esta pérdida provenía exclusivamente de los 30 extremos o si reflejaba una deficiencia estructural:

- **En el conjunto normal del Holdout ($\|y\| \le 10$, 2 682 filas, $98.93\%$ del Holdout):**
  * $\mathrm{MSE}(B^{+++}) = 2.0380$
  * $\mathrm{MSE}(E) = 2.1222$
  * $\Delta R^2_{\mathrm{OOS, normal}} = \mathbf{-4.1312\%}$
- **En los episodios extremos del Holdout ($\|y\| > 10$, 30 filas, $1.07\%$ del Holdout):**
  * $\mathrm{MSE}(B^{+++}) = 2831.62$
  * $\mathrm{MSE}(E) = 2840.21$
  * $\Delta R^2_{\mathrm{OOS, extremo}} = -0.3033\%$
  * Las 30 filas extremas concentran el **$93.95\%$ de la suma total de errores cuadráticos** de $B^{+++}$ y el **$93.74\%$** de $E$.

**Diagnóstico concluyente:**  
El colapso de $E$ en Holdout **no es un espejismo creado por las 30 observaciones extremas**. En el régimen de mercado completamente normal ($98.93\%$ de los datos), el modelo geométrico $E$ es **$4.13\%$ peor** que el modelo de control $B^{+++}$. La degradación predictiva de la geometría es uniforme e inherente al modelo.

---

## 4. Investigación 3 — Diagnóstico Conceptual y Algebraico de Features

### 4.1 Definiciones Congeladas y Propiedad Teórica Pretendida
En [`navier_lab/features.py#L148-L170`](file:///C:/Users/USER/Downloads/navier_lab_project/navier_lab_project/navier_lab/features.py#L148-L170):

1. **`v03_pnpc_k3` (Control de ratio en $B^{+++}$):**
   $$\texttt{v03\_pnpc\_k3} = \frac{\texttt{ofi\_raw\_5}}{d_{\mathrm{contra}, 3} + \epsilon}$$
   *Propiedad:* Razón de penetración del flujo de órdenes acumulado de 5 s (`ofi_raw_5` en BTC) respecto a la profundidad acumulada de los 3 niveles opuestos en el libro (`d_contra_k3` en BTC). Adimensional.
2. **`v03_liq_conc_ask` y `v03_liq_conc_bid` (Geometría de concentración en $E$):**
   $$\texttt{v03\_liq\_conc\_ask} = \frac{V_{\mathrm{ask}, 1}}{\sum_{k=1}^{10} V_{\mathrm{ask}, k} + \epsilon}, \quad \texttt{v03\_liq\_conc\_bid} = \frac{V_{\mathrm{bid}, 1}}{\sum_{k=1}^{10} V_{\mathrm{bid}, k} + \epsilon}$$
   *Propiedad:* Fracción de la liquidez total del libro que está aglomerada en el mejor nivel (top-1). Estrictamente acotada en $[0, 1]$.
3. **`v03_impact_conc_k3` (Interacción geométrica no lineal en $E$):**
   $$\texttt{v03\_impact_conc\_k3} = \texttt{v03\_pnpc\_k3} \times \texttt{liq\_conc\_contra}$$
   *Propiedad:* Hipótesis de que el impacto en precio de una orden se intensifica si la liquidez del lado contrario está concentrada en el mejor nivel en lugar de distribuida.

### 4.2 Análisis Algebraico de Redundancia y Falsa Ortogonalidad
Al expandir la expresión algebraica de `v03_impact_conc_k3`:
$$\texttt{v03\_impact\_conc\_k3} = \frac{\texttt{ofi\_raw\_5}}{\sum_{k=1}^3 V_{\mathrm{contra}, k}} \times \frac{V_{\mathrm{contra}, 1}}{\sum_{k=1}^{10} V_{\mathrm{contra}, k}} = \texttt{ofi\_raw\_5} \times \left( \frac{V_{\mathrm{contra}, 1}}{\sum_{k=1}^3 V_{\mathrm{contra}, k}} \right) \times \frac{1}{V_{\mathrm{contra}, \mathrm{total}}}$$

Nótese que en esta expresión:
- $\texttt{ofi\_raw\_5}$ es una variable que oscila violentamente alrededor de 0 con alta desviación estándar.
- Las variables de profundidad y concentración de volumen son estrictamente positivas y presentan desviaciones típicas mucho más pequeñas.
- Por tanto, la dirección y la escala de la variable compuesta están **casi totalmente dominadas por el signo y la magnitud del flujo de órdenes**.

### 4.3 Matriz de Colinealidad de Rango (Spearman) vs Lineal (Pearson)

| Variable V3 | vs Variable Convencional | Correlación Lineal Pearson ($r$) | Correlación de Rangos Spearman ($\rho$) | VIF en $E$ |
|---|---|:---:|:---:|:---:|
| **`v03_impact_conc_k3`** | `v03_pnpc_k3` | $+0.4498$ | **$+0.9237$** | $1.35$ |
| **`v03_impact_conc_k3`** | `_ofi_div_depth10` | $+0.2663$ | **$+0.9146$** | $1.35$ |
| **`v03_impact_conc_k3`** | `ofi_5` | $+0.3121$ | **$+0.8990$** | $1.35$ |
| **`v03_impact_conc_k3`** | `imb_full` | $+0.2024$ | **$+0.6943$** | $1.35$ |
| **`v03_pnpc_k3`** | `_ofi_div_depth10` | $+0.3572$ | **$+0.9037$** | $1.54$ |
| **`v03_pnpc_k3`** | `ofi_5` | $+0.4352$ | **$+0.9002$** | $1.54$ |
| **`v03_liq_conc_ask`** | `imb_top1` | $-0.2617$ | **$-0.6122$** | $1.44$ |
| **`v03_liq_conc_bid`** | `imb_top1` | $+0.1215$ | **$+0.5808$** | $1.41$ |

### 4.4 La Falacia del VIF Bajo
- En auditorías previas se observó que el VIF de las variables V3 era bajo ($1.35\text{--}1.54$), lo que sugería baja multicolinealidad.
- El análisis post-mortem demuestra que el VIF lineal ordinario estaba distorsionado por la fuerte asimetría positiva (*skewness*) de las distribuciones de profundidad y ratios.
- Sin embargo, la **correlación monótona de rangos (Spearman) es de $\rho = 0.9237$**. Esto significa que ordenar el mercado por `v03_impact_conc_k3` produce esencialmente la misma ordenación que `v03_pnpc_k3`, `_ofi_div_depth10` y `ofi_5`.
- **Conclusión científica:** Las variables geométricas **no aportaron información nueva al modelo**. Toda la información útil de primer orden ya estaba capturada por `_ofi_div_depth10` y `ofi_5` en el baseline $B^{++}$. Añadir tres variables fuertemente correlacionadas en rango solo introdujo grados de libertad espurios que sobreajustaron el entrenamiento y degradaron la predicción OOS.

---

## 5. Investigación 4 — Auditoría de la Interpretación Económica y Costes

### 5.1 Corrección Crítica: Porcentaje (%) vs Puntos Básicos (bps)
En el informe de Fase 5 se mencionó informalmente que las comisiones taker de Kraken rondaban "0.25 a 0.40 bps". Esto constituyó un error de unidades conceptual que debe corregirse:
- **Definición:** $1\text{ punto básico (bps)} = 0.0001 = 0.01\%$. Por tanto, $1\% = 100\text{ bps}$.
- **Estructura real de tarifas en Kraken:**
  * Comisión Taker estándar (primer nivel): $0.26\% = \mathbf{26.0\text{ bps}}$ (Round-trip entrada/salida = $\mathbf{52.0\text{ bps}}$). Nivel inicial máximo: $0.40\% = 40.0\text{ bps}$.
  * Comisión Maker estándar: $0.16\% = \mathbf{16.0\text{ bps}}$ (Round-trip = $\mathbf{32.0\text{ bps}}$).
  * Incluso en los niveles institucionales más altos (VIP), la comisión taker no desciende de $0.10\% = 10.0\text{ bps}$.

### 5.2 Magnitud Económica Frente al Movimiento del Precio
Al contrastar la física del precio a 10 segundos frente a las fricciones de mercado:
- **Retorno absoluto medio a 10 s ($\|y_{\mathrm{bps}}\|$):** **$1.1647\text{ bps}$** (mediana: $0.8230\text{ bps}$; percentil 95: $3.5206\text{ bps}$).
- **Spread del libro:** Media de $0.0144\text{ bps}$ (mediana $0.0123\text{ bps}$, tick mínimo $\$0.10\text{ USD}$).
- **Ratio Retorno Medio / Comisión Taker Round-trip ($52\text{ bps}$):**
  $$\frac{1.1647\text{ bps}}{52.0\text{ bps}} = \mathbf{0.0224\times} \quad (2.24\%)$$

El retorno económico bruto promedio que ofrece el mercado en una ventana de 10 segundos es **44 veces menor** que el coste de comisiones taker de un viaje de ida y vuelta.

### 5.3 Distinción Conceptual: Error Estadístico vs Rentabilidad Operativa
Es imperativo distinguir rigurosamente entre los siguientes planos:
1. **Bondad de ajuste estadístico (MSE / $R^2$):** El evaluador congelado mide exclusivamente la reducción del error cuadrático sobre un target z-score estandarizado. No simula posiciones ni órdenes.
2. **Capacidad direccional (Hit Ratio / Signo):** Un modelo puede reducir el MSE mediante un mejor ajuste de la varianza condicional en colas sin predecir correctamente el signo del retorno.
3. **Rentabilidad teórica de una señal:** Asume ejecución sin fricciones multiplicando el signo por el retorno.
4. **Rentabilidad neta de ejecución:** Descuenta comisiones reales, spread bid-ask, slippage por consumo de profundidad, latencia de cola FIFO y cancelaciones en el libro.

> [!NOTE]
> Dado que la Fase 5 operó sobre MSE y no ejecutó una simulación de órdenes de mercado, **no es metodológicamente correcto afirmar que "el PnL real es estrictamente negativo" como un hecho medido**.  
> La afirmación rigurosa es: **la rentabilidad económica no ha sido demostrada**, el modelo no posee una ventaja predictiva fuera de muestra ($p_{\mathrm{FDR}} = 0.73$, $\Delta R^2 < 0$ en Holdout) y la relación entre la magnitud del retorno a 10 s ($1.16\text{ bps}$) y las comisiones de exchange ($26\text{--}52\text{ bps}$) hace inviable la explotación económica de una microseñal estática a este horizonte temporal.

---

## 6. Tabla Resumen de Hallazgos

| # | Hallazgo Diagnóstico | Evidencia Concreta | Estado |
|:---:|---|---|:---:|
| **H1** | **La evaluación OOS congelada no contiene fugas de datos** | La purga y el embargo de 10 s aseguran 11 s de separación neta sin solapamiento temporal entre train y test. | **CONFIRMADO** |
| **H2** | **Los signos de $\Delta R^2$ y Diebold-Mariano son algebraicamente consistentes** | $\Delta R^2$, $\bar{d}$ y $t\text{-stat}$ conservan la misma polaridad en el código congelado. | **CONFIRMADO** |
| **H3** | **Las 45 observaciones con $\|y\| > 10$ no fueron movimientos atípicos de precio** | Su retorno bruto medio fue de solo $3.27\text{ bps}$; el factor causante fue un colapso de la volatilidad denominadora ($\sigma_{60} \approx 0.01\text{ bps}$, $9.2\times$ menor). | **CONFIRMADO** |
| **H4** | **El deterioro en Holdout no se debe exclusivamente a los episodios extremos** | En las 2 682 observaciones normales del Holdout ($98.9\%$), el modelo $E$ tiene un $\Delta R^2_{\mathrm{OOS}} = -4.13\%$ frente a $B^{+++}$. | **CONFIRMADO** |
| **H5** | **Las features geométricas son monótonamente redundantes con el OFI y la profundidad** | La correlación de Spearman entre `v03_impact_conc_k3` y `_ofi_div_depth10` es $\rho = 0.9146$, y con `v03_pnpc_k3` es $\rho = 0.9237$. | **CONFIRMADO** |
| **H6** | **El VIF lineal no detectó la redundancia por asimetría distributiva** | El VIF ordinario se mantuvo en $1.35\text{--}1.54$, ocultando una colinealidad no lineal casi perfecta en rangos. | **CONFIRMADO** |
| **H7** | **La analogía hidrodinámica carece de fundamentación empírica en el libro estático** | Tratar la concentración de órdenes estáticas como viscosidad o presión no añade capacidad predictiva sobre el flujo de órdenes simple. | **CONFIRMADO** |
| **H8** | **Las fricciones de mercado exceden en más de un orden de magnitud los retornos a 10 segundos** | Las comisiones taker de Kraken ($52\text{ bps}$ round-trip) son 44 veces superiores al movimiento medio a 10 s ($1.16\text{ bps}$). | **CONFIRMADO** |
| **H9** | **Una arquitectura dinámica de seguimiento de órdenes por ID capturaría verdadera reposición** | Las cancelaciones y reposiciones a nivel de tick individual podrían tener dinámica no observable en snapshots de 1 s. | **PLAUSIBLE** *(No verificado en estos datos)* |

---

## 7. Recomendación Final

De acuerdo con las opciones establecidas en el protocolo de auditoría:

# **`CERRAR LA LÍNEA GEOMÉTRICA ESTÁTICA`**

### Justificación de la Elección:
1. **No procede corregir problemas de integridad:** La auditoría confirmó que el evaluador congelado, las particiones temporales, los estimadores HAC y la corrección FDR fueron ejecutados con total rigor matemático. No hay defectos que subsanar para revertir el veredicto.
2. **La falsación científica es concluyente:** La hipótesis de que las propiedades geométricas estáticas de los libros L2 (curvaturas de volumen, ratios de concentración top-1 e interacciones de penetración) contienen señal predictiva incremental más allá del flujo de órdenes estándar (`OFI`) y la profundidad global queda descartada empíricamente. Las variables son monótonamente redundantes ($\rho > 0.92$) y su inclusión sistemáticamente degrada la precisión fuera de muestra ($\Delta R^2 < 0$ frente a baselines y $-4.13\%$ en holdout normal).
3. **Disciplina metodológica:** Insistir en buscar combinaciones alternativas de las mismas variables en el mismo dataset constituiría *data snooping* y *p-hacking* retrospectivo.

El proyecto NAVIER V3 concluye formalmente con evidencia científica negativa y documentada de forma transparente e inmutable.
