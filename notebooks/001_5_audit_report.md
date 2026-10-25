# NAVIER 001.5 — Informe de Auditoría Técnica y Estadística

> **Estado:** Auditoría completada sobre datos sintéticos (V0.1).  
> **Propósito:** Registrar formalmente las respuestas empíricas, diagnósticos numéricos y estado de validación del [001_5_navier_audit.ipynb](file:///c:/Users/USER/Downloads/navier_lab_project/navier_lab_project/notebooks/001_5_navier_audit.ipynb) antes de conectar datos de mercado real.

---

## 1. Entorno de Ejecución y Trazabilidad

Se ejecutó la suite de dependencias en un entorno virtual aislado (`venv`), con las versiones exactas especificadas en [requirements.txt](file:///c:/Users/USER/Downloads/navier_lab_project/navier_lab_project/requirements.txt):

* **Python:** 3.10.9 (Windows AMD64)
* **numpy:** 2.2.6
* **pandas:** 2.3.3
* **pyarrow:** 24.0.0
* **scipy:** 1.15.3
* **statsmodels:** 0.15.0
* **matplotlib:** 3.10.9
* **pytest:** 8.4.2
* **nbformat:** 5.11.1 / **nbclient:** 0.11.0

### Verificación de Regresión (Tests Unitarios V0.1)
* `pytest tests/test_pipeline.py`: **5/5 pruebas aprobadas** (100% de éxito en 3.87 s).

---

## 2. Integridad de Datos (Snapshots L2)

Se auditó el dataset de snapshots crudos (`raw`, 12 000 filas de snapshots a 1 segundo) para comprobar el cumplimiento de los contratos de integridad:

| Chequeo de Integridad | Resultado Auditado | Diagnóstico |
|---|---|---|
| Columnas faltantes (`missing_columns`) | **0** | Todas las columnas del esquema existen |
| Celdas numéricas no finitas (`NaN`, `Inf`) | **0** | Sin valores corruptos en raw |
| Cantidades no positivas ($Q \le 0$) | **0** | Todas las cantidades bid/ask son > 0 |
| Libros cruzados o bloqueados ($ask_1 \le bid_1$) | **0** | Spread positivo estricto en el 100% |
| Monotonía en precios Bid ($bid_k > bid_{k+1}$) | **0** | Niveles de compra estrictamente descendentes alejándose del BBO |
| Monotonía en precios Ask ($ask_k < ask_{k+1}$) | **0** | Niveles de venta estrictamente ascendentes alejándose del BBO |
| Timestamps duplicados | **0** | Serie temporal unívoca |
| Saltos temporales o irregularidades ($\Delta t \ne 1\text{s}$) | **0** | Rejilla regular perfecta de 1 s |

> **Nota sobre el dataset auditado (A-08):** Esta auditoría evaluó una muestra controlada generada en memoria con `S.generate("S2_navier", n=12000, seed=17)` (12 000 filas). El dataset sintético completo de V0.1 consta de 100 000 filas archivadas en [data/synthetic/raw_S2_navier.parquet](file:///c:/Users/USER/Downloads/navier_lab_project/navier_lab_project/data/synthetic/raw_S2_navier.parquet) (SHA256: `52d3f1213fe7b869...`). En la versión 001.6 se incluirán pruebas automáticas que cubran tanto los generadores sintéticos como los archivos persistidos.

---

## 3. Comportamiento Numérico de Features

Conteo de valores no finitos e inicialización por tamaño de ventana móvil ($W$):

* **Valores infinitos (`+Inf` / `-Inf`):** **0** en todas las 24 variables numéricas.
* **Valores `NaN` iniciales (esperados por ventanas retrospectivas):**
  * `vol60_bps`: 60 (ventana móvil de 60 s de retornos).
  * `re_log` / `re_m`: 60 (dependiente de `vol60_bps`).
  * `ofi_5`: 59 (acumulación de 5 s normalizada por ventana de volumen de 60 s).
  * `ret_30`: 30; `imb_full_lag8`: 8; `dI_dt`: 7; `ret_5` / `imb_full_lag5`: 5; `u`: 4; `imb_full_lag2`: 2; `ret_1`: 1.
  * Todas las variables estáticas y de nivel instantáneo (`spread_bps`, `depth_log`, `imb_full`, `grad_bid`, `grad_ask`, etc.): **0 NaNs**.

---

## 4. Auditoría de Fórmulas y Sentido Económico

### 4.1. Gradientes y Curvaturas de Liquidez (`grad_bid`, `grad_ask`)
* **Mecanismo:** Proyección sobre polinomios ortogonales normalizados por la media de las 20 cantidades (10 bid + 10 ask).
* **Distribución empírica:**
  * Denominador (media de 20 cantidades): cuantiles `[0.59, 0.89, 1.20, 1.52, 2.51]`. No se aproxima a cero.
  * `grad_bid`: min `-0.4106`, mediana `+0.0586`, max `+0.6962`.
  * `grad_ask`: min `-0.4097`, mediana `+0.0716`, max `+0.6982`.
* **Interpretación económica auditada:**
  * Dado que el índice $k \in [1..10]$ aumenta desde el BBO hacia niveles profundos, **un gradiente positivo significa mayor concentración de volumen lejos del BBO**, no cerca del spread.
  * La normalización conjunta ($norm = \text{mean}(V_{bid} + V_{ask})$) introduce acoplamiento entre ambos lados del libro.

### 4.2. Número de Reynolds de Mercado ($Re_m$ y `re_log`)
* **Fórmula:** $Re_m = \frac{|u| \cdot L_{bps}}{\sigma_{60}^2}$.
* **Auditoría numérica:**
  * Conteos con $\sigma_{60} < 10^{-8}$: **0**.
  * Cuantiles de $Re_m$ finito: `[2.57e-08, 0.2439, 0.8778, 1.2876, 2.1563]`.
  * Correlación entre `re_log` y $\sigma_{60}$: **-0.2624**.
* **Observación crítica:**
  * $L_{bps}$ mide la distancia entre el nivel 10 ask y el nivel 10 bid en bps. No es adimensional por naturaleza a menos que se fijen convenciones temporales explícitas. Si en datos reales de baja liquidez $\sigma_{60} \to 0$, $Re_m$ requerirá un suelo de volatilidad (`clip` o $\epsilon$) para evitar inestabilidad.

### 4.3. Aceleración de Imbalance ($dI/dt$) y Colinealidad
* Matriz de correlación de Spearman contra imbalance y sus rezagos:

| Variable | `imb_full` | `imb_full_lag2` | `imb_full_lag5` | `imb_full_lag8` | `dI_dt` |
|---|---|---|---|---|---|
| **`imb_full`** | 1.000 | 0.954 | 0.891 | 0.835 | **+0.236** |
| **`imb_full_lag2`** | 0.954 | 1.000 | 0.932 | 0.871 | **+0.145** |
| **`imb_full_lag5`** | 0.891 | 0.932 | 1.000 | 0.932 | **-0.148** |
| **`imb_full_lag8`** | 0.835 | 0.871 | 0.932 | 1.000 | **-0.229** |
| **`dI_dt`** | +0.236 | +0.145 | -0.148 | -0.229 | **1.000** |

* **Conclusión auditada:** $dI/dt$ tiene correlación positiva moderada con el imbalance contemporáneo y correlación negativa con rezagos lejanos ($t-8$). No es ortogonal por construcción, por lo que **solo debe evaluarse su significancia como variable incremental sobre el modelo B+** (que ya incluye los rezagos lineales), nunca de forma aislada.

---

## 5. Causalidad y Target

### 5.1. Chequeo de Fuga Temporal (Look-Ahead Bias)
* Se fijó $t_0 = N/2$. Se mutó todo el futuro ($t > t_0$) de todas las variables crudas con ruido gaussiano del 3%.
* **Diferencia máxima en features calculadas para $t \le t_0$:** **0.000000**.
* **Veredicto:** **Causalidad estricta verificada**. Ningún cálculo de variables lee hacia adelante.

### 5.2. Definición del Target
* Comparación entre el target manual $10^4 \cdot (\ln(\text{mid}_{t+H}) - \ln(\text{mid}_t))$ y `y_bps`:
* **Diferencia absoluta máxima:** **$1.438 \times 10^{-11}$ bps** (error de redondeo flotante nulo).

---

## 6. Purga Temporal y Folds Fuera de Muestra

Diseño: Purged Walk-Forward en 5 folds, con $H = 10$:

| Fold | Último train (`idx`) | Primer test (`idx`) | Gap de purga | Fin de etiqueta último train (`idx + H`) | ¿Solapamiento con test? (`label_overlap_test`) |
|---|---|---|---|---|:---:|
| **1** | 1977 | 1988 | 10 | 1987 | **False** ✅ |
| **2** | 3965 | 3976 | 10 | 3975 | **False** ✅ |
| **3** | 5954 | 5965 | 10 | 5964 | **False** ✅ |
| **4** | 7942 | 7953 | 10 | 7952 | **False** ✅ |
| **5** | 9930 | 9941 | 10 | 9940 | **False** ✅ |

* **Veredicto:** **Cero solapamiento de etiquetas**. La purga de $H$ pasos asegura que ninguna observación en entrenamiento utilice retornos que abarquen el conjunto de prueba.

---

## 7. Matriz de Hallazgos y Decisiones para V0.2 / Captura Real

| ID | Hallazgo | Severidad | Acción antes de capturar datos reales |
|---|---|---|---|
| **A-01** | `Re_m` puede desestabilizarse en regímenes de volatilidad extremadamente baja ($\sigma_{60} \to 0$). | Alta | Documentar unidades explícitas e introducir suelo de volatilidad $\epsilon > 0$ en la versión V0.2. |
| **A-02** | `L_bps` representa el spread nivel 10 a nivel 10, no el volumen total acumulado. | Media | Mantenerlo documentado como ancho total del libro observable. |
| **A-03** | `to_1s_grid` no arrastra el segundo incompleto entre chunks consecutivos. | Alta para streaming | Diseñar estado persistente en el buffer del recolector para el remanente sub-segundo. |
| **A-04** | Normalización de gradientes sensible a órdenes anómalas en un solo lado del libro. | Media | Comparar en V0.2 si la normalización por lado individual aporta estabilidad. |
| **A-05** | $dI/dt$ presenta colinealidad con la reversión de imbalance. | Media | Mantener la regla pre-registrada: evaluar exclusivamente a través del $\Delta R^2$ OOS sobre B+. |

---

### Criterio de Pase a Datos Reales (Gate)
1. ✅ **Reproducibilidad:** Entorno virtual congelado y suite de pruebas aprobada.
2. ✅ **Causalidad:** Cero look-ahead en features y cero solapamiento en purga walk-forward.
3. ⏳ **Paso siguiente:** Endurecer el recolector L2 streaming con acarreo de segundos y validación de orden antes de conectar a Kraken/Binance.
