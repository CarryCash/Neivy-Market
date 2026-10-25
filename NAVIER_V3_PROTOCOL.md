# NAVIER V3 — Protocolo Científico Congelado
## Liquidity-Conditioned Price Impact

**Versión:** 3.0.0  
**Fecha de congelación:** 2026-10-22  
**Estado:** PRE-REGISTRO — no abrir datos de validación hasta completar la Fase 3  
**Basado en:** Diagnóstico post-mortem de NAVIER V2 (veredicto: FRACASO, sesiones 1–11)

---

> **Regla de integridad científica:** Este documento debe congelarse *antes* de construir las features V3 y *antes* de consultar los datos del bloque temporal de validación independiente. Cualquier modificación posterior a esa apertura debe registrarse como desviación y no puede convertirse en análisis confirmatorio.

---

## 1. Motivación y diagnóstico de V2

Los resultados de NAVIER V2 (sesiones 1–11, 7 364 observaciones, evaluación walk-forward sobre 80%) arrojaron:

| Comparación | ΔR²_OOS (WF) | p-valor DM (FDR) | Consistencia folds |
|---|---|---|---|
| C (V0.1) vs B | −0.000 | 0.916 | 1/4 positivos |
| C (V0.1) vs B+ | −0.008 | 0.367 | 1/4 positivos |
| D (V0.2) vs B | −0.004 | 0.367 | 2/4 positivos |
| D (V0.2) vs B+ | −0.011 | 0.367 | 2/4 positivos |

**Diagnóstico:** Las variables fluidas de V0.1/V0.2 describieron el estado del mercado sin aportar información predictiva *incremental*. El análisis univariado previo detectó que varias quedaban absorbidas por `imb_full` y sus rezagos (VIF 50–180). V0.2 introdujo mejoras dimensionales que tampoco superaron B+.

**Lección metodológica:** una variable puede describir el fluido sin predecirlo. El problema no era la escala ni la normalización; era que la hipótesis no especificaba el *mecanismo causal* por el que la analogía física debería generar información nueva sobre la respuesta del precio.

---

## 2. Nueva hipótesis — NAVIER V3

### H1 (hipótesis primaria, falsable)

> El mismo desequilibrio de órdenes (OFI / imbalance) produce movimientos de precio cuantitativamente distintos según el estado local y cambiante de la liquidez del lado contrario del libro L2 en ese instante.

**Predicción falsable:**  
Un modelo que combine el flujo de órdenes con la *vulnerabilidad local de liquidez* mejorará la predicción del retorno futuro (mid-price, horizonte 10 s) sobre el conjunto de validación temporal independiente, frente a los baselines B y B++ que ya conocen el flujo, el imbalance, la profundidad y sus rezagos.

**Analogía física (operacional, no literal):**  
La presión no determina sola el desplazamiento; la resistencia del medio importa. En el mercado, esa "resistencia" no es una viscosidad física: es una magnitud empírica de microestructura medible en el libro L2. Si la analogía genera predicciones mejores que el baseline más fuerte disponible, la evidencia es favorable; si no lo hace, la analogía no merece mantenerse por su elegancia.

### H1a (sub-hipótesis, solo exploratoria en esta versión)

> La velocidad de reposición o agotamiento de la liquidez del lado contrario añade información incremental sobre H1, más allá de la vulnerabilidad instantánea.

H1a se explorará solo después de fijar la evaluación de H1. No puede convertirse retroactivamente en hipótesis principal.

---

## 3. Definición exacta de variables

### 3.1 Variables de presión (ya existentes — NO modificar)

- **OFI** (`ofi_5`): Order Flow Imbalance acumulado 5 s, normalizado por profundidad media top-of-book (60 s). Fórmula exacta en `features.py` línea 98–102.  
- **Imbalance** (`imb_full`): `(Vb − Va) / (Vb + Va)`, suma de 10 niveles. Línea 90–91.

### 3.2 Variables de resistencia / vulnerabilidad — NAVIER V3 (nuevas)

Todas causales: calculadas exclusivamente con información disponible en el instante `t`.

#### Variable central: Presión normalizada por profundidad contraria (PNPC)

Para preservar la coherencia dimensional estricta (Opción A auditada), se utiliza el flujo bruto de órdenes acumulado en 5 segundos (`ofi_raw_5`, en BTC) y se divide por la profundidad acumulada del lado contrario (en BTC):

```
pnpc_k_t = ofi_raw_5_t / (depth_contra_k_t + ε)
```

Donde:
- `ofi_raw_5_t` = $\sum_{i=0}^4 e_{t-i}$ en unidades de moneda base (BTC).
- `depth_contra_k_t` = volumen acumulado en los primeros `k` niveles del lado que recibe la presión (ask si `ofi_raw_5` $\ge 0$, bid si `ofi_raw_5` $< 0$), en unidades de moneda base (BTC).
- `k` = 3 (primario), `k` = 5 (robustez).
- `ε` = 1e-6 (suelo numérico).
- **Unidades:** $\frac{\text{BTC}}{\text{BTC}} = \mathbf{1}$ (estrictamente adimensional, representa la tasa de penetración instantánea sobre el libro).

#### Variable de distribución de liquidez (concentración geométrica)

```
liq_conc_side_t = qty_level1_side_t / (total_qty_side_t + ε)
```

Fracción adimensional de liquidez en el primer nivel respecto al total de 10 niveles del mismo lado: $\frac{\text{BTC}}{\text{BTC}} = \mathbf{1}$. Valores altos = liquidez concentrada en el mejor precio (mayor vulnerabilidad geométrica). Calculada por separado para bid y ask.

#### Variable de dinámica de reposición (EXPLORATORIA — solo H1a)

```
depth_replenish_side_t = (depth_k_side_t - depth_k_side_{t-τ}) / (depth_mean60_side_t + ε)
```

Variación de profundidad en ventana `τ = 5 s`, normalizada por la profundidad media histórica de 60 s del mismo lado. Ambas magnitudes en BTC $\implies$ razón adimensional. Invalidada (NaN) si existe discontinuidad (`GAP_DISCONTINUITY`) en los últimos 5 s o si la historia de 60 s está corrompida.

#### Variable de interacción presión × concentración

```
impact_conc_k3_t = pnpc_k3_t × liq_conc_contra_t
```

Donde `liq_conc_contra` es la concentración del lado contrario al flujo neto. Producto de dos magnitudes adimensionales $\implies$ adimensional.

### 3.3 Nomenclatura en código

```python
NAVIER_V3_RATIO = [
    "v03_pnpc_k3",          # presión bruta / depth_contra(k=3) [adimensional]
    "v03_pnpc_k5",          # presión bruta / depth_contra(k=5) [robustez]
]
NAVIER_V3_GEOMETRY = [
    "v03_liq_conc_ask",     # concentración top-1 en ask [adimensional]
    "v03_liq_conc_bid",     # concentración top-1 en bid [adimensional]
    "v03_impact_conc_k3",   # pnpc_k3 × liq_conc_contra [adimensional]
]
NAVIER_V3_CORE = NAVIER_V3_RATIO + NAVIER_V3_GEOMETRY
NAVIER_V3_REPLENISH = [
    "v03_depth_replenish_ask",   # dinámica ask (exploratorio H1a)
    "v03_depth_replenish_bid",   # dinámica bid (exploratorio H1a)
]
```

---

## 4. Baselines y familias de modelos

### Modelo B (referencia mínima convencional)
`spread_bps, depth_log, vol60_bps, imb_full, imb_top1, ofi_5, ret_1, ret_5, ret_30`

### Modelo B+ (referencia temporal)
B + `imb_full_lag2, imb_full_lag5, imb_full_lag8`

### Modelo B++ (baseline con interacciones convencionales de libro)
B+ + producto cruzado `ofi_5 × imb_full` + penetración convencional sobre profundidad total `ofi_raw_5 / (exp(depth_log) + ε)`.  
*(Nota crítica de auditoría dimensional: se sustituye la formulación matemáticamente errónea previa `ofi_5 / (exp(depth_log) + ε)` —cuya dimensión era $\mathrm{BTC}^{-1}$ al dividir un ratio ya normalizado por la profundidad media histórica entre la profundidad total— por la penetración física directa `ofi_raw_5 / (exp(depth_log) + ε)`, con unidades $\frac{\mathrm{BTC}}{\mathrm{BTC}} = \mathbf{1}$ estrictamente adimensionales).*

### Modelo B+++ (baseline de control de razón de profundidad — DECISIVO)
B++ + `v03_pnpc_k3`.  
**Justificación metodológica:** B+++ controla formalmente la hipótesis del cociente entre presión y profundidad contraria. Permite aislar si la distribución geométrica de la liquidez aporta algo una vez que el modelo ya conoce esa razón.

### Modelo E — NAVIER V3 (hipótesis confirmatoria de geometría)
B+++ + NAVIER_V3_GEOMETRY (`v03_liq_conc_ask`, `v03_liq_conc_bid`, `v03_impact_conc_k3`).  
**El contraste confirmatorio principal es E vs B+++.**

### Modelo E_H1a — NAVIER V3 exploratorio (dinámica de reposición)
E + NAVIER_V3_REPLENISH (análisis post-hoc exclusivo, nunca confirmatorio).

---

## 5. Objetivo primario — formalización matemática

```
r10_norm(t) = [ ln(mid(t+10) / mid(t)) × 10^4 ] / [ σ̂₆₀,bps(t) × √10 ]
```

- Numerador: retorno logarítmico a 10 segundos en puntos básicos (**bps**).
- Denominador: volatilidad realizada causal de 60 s expresada en **bps** escalada por $\sqrt{10}$.
- Razón: $\frac{\text{bps}}{\text{bps}} = \mathbf{1}$ (z-score adimensional estándar).
- Exclusiones de validez: $\hat{\sigma}_{60}(t) < 0.01\text{ bps}$, discontinuidad (`GAP_DISCONTINUITY`) en cualquier punto de $(t, t+10]$, o `staleness_ms` futuro $> 1000\text{ ms}$.
- Exclusiones: `σ̂₆₀(t) < 0.01 bps`, gap en `[t, t+10]`, staleness futuro > 1000 ms.
- Horizonte secundario (robustez, no confirmatorio): 5 s y 30 s.

---

## 6. Algoritmo de ajuste

**OLS con regularización ridge mínima** (`λ = 1e-6 × N_train`), normalización z-score estricta sobre train — idéntico a V2.

Análisis exploratorio adicional permitido: **árbol de gradiente** con máx. 2 niveles de profundidad, hiperparámetros congelados en `(n_estimators=100, max_depth=2, learning_rate=0.05)`. Sus resultados van separados, etiquetados como exploración. No pueden convertirse en el test confirmatorio.

---

## 7. Protocolo de validación temporal

### Datos contaminados (sesiones 1–11, uso permitido)
- Desarrollo y verificación del pipeline de features V3.
- Análisis exploratorio etiquetado.
- **No confirmar H1 con estos datos.**

### Bloque de validación independiente (captura nueva)
- Mismo par/exchange/configuración que sesiones 1–11.
- Mínimo 9 sesiones de ~40 min en franjas horarias variadas.
- Almacenados en `data/v3_validation/`.
- Cerrado hasta congelar el modelo completamente (antes de Fase 5).
- Mínimo requerido: **≥ 6 500 observaciones limpias**.

### Esquema walk-forward (sin cambios)
- Hold-out final intocable: último 20%.
- Walk-forward expansivo: k = 5 folds.
- Purga: 10 obs. al final de cada bloque de entrenamiento.
- Embargo: 10 obs. entre entrenamiento y test.
- Normalización: solo sobre train de cada fold.

---

## 8. Comparaciones y criterios de aceptación formales

### 8.1 Jerarquía de contrastes preespecificados

| ID | Contraste | Tipo | Rol metodológico |
|---|---|---|---|
| **C1** | **E vs B+++** | **Confirmatorio (Principal)** | **Aísla el valor incremental de la concentración y geometría de liquidez controlando la razón de presión/profundidad** |
| C2 | E vs B++ | Confirmatorio (Secundario) | Evalúa valor frente a interacciones convencionales globales |
| C3 | E vs B+ | Confirmatorio (Secundario) | Comparabilidad con V2 (control autorregresivo) |
| C4 | E vs B | Confirmatorio (Secundario) | Referencia histórica mínima |
| C5 | E_H1a vs E | Exploratorio | Evalúa dinámicas de reposición sobre su submuestra limpia |

### 8.2 Regla de Muestra Común
Todos los modelos confirmatorios ($B, B+, B++, B+++, E$) se entrenan y evalúan estrictamente sobre la **misma muestra común de observaciones válidas** (donde todas las variables de $E$ y el target son no-nulos). Esto previene sesgos de selección o cambios en la composición muestral.

### 8.3 Matriz de Decisión Unívoca (MECE) sobre C1 (E vs B+++)

Se preestablece un umbral de futilidad de relevancia mínima práctica: $\delta_{\min} = 0.0010$ ($+0.10\%$ de ganancia de $R^2_{\mathrm{OOS}}$). Con $k=5$ folds se generan 4 splits de test; el requisito de consistencia es de al menos 3 de 4 folds positivos ($\ge 75\%$).

**Orden Determinista de Clasificación (Jerarquía Estricta MECE):**  
Para garantizar que ningún resultado experimental pueda satisfacer simultáneamente dos categorías (p. ej., casos con $\Delta R^2_{\mathrm{OOS}}(\mathrm{WF}) \ge \delta_{\min}$, $p_{\mathrm{DM, FDR}} \ge 0.05$ pero $< 2/4$ folds positivos, que antes satisfacían simultáneamente Fracaso e Inconclusión, o casos con $0 < \Delta R^2 < \delta_{\min}$ y $< 2/4$ folds que satisfacían Fracaso y Futilidad), se establece la siguiente secuencia determinista:

1. **Candidato a Éxito en Walk-Forward ($A_{\mathrm{WF}}$):** Requiere $\Delta R^2_{\mathrm{OOS}}(\mathrm{WF}) \ge \delta_{\min}$, $p_{\mathrm{DM, FDR}} < 0.05$ y consistencia $\ge 3/4$ folds con $\Delta R^2 > 0$.
   - Si se cumple $A_{\mathrm{WF}}$ y en Holdout $\Delta R^2_{\mathrm{OOS}}(\mathrm{HO}) > 0$ con $p_{\mathrm{DM}}(\mathrm{HO}) < 0.05$ $\implies$ **ÉXITO**.
   - Si se cumple $A_{\mathrm{WF}}$ pero en Holdout $\Delta R^2_{\mathrm{OOS}}(\mathrm{HO}) \le 0$ o $p_{\mathrm{DM}}(\mathrm{HO}) \ge 0.05$ $\implies$ **DISCREPANCIA HOLDOUT**.
2. **Si no se cumple $A_{\mathrm{WF}}$:**
   - **FRACASO (Falsación):** Si $\Delta R^2_{\mathrm{OOS}}(\mathrm{WF}) \le 0$ **O** $< 2/4$ folds positivos ($< 50\%$). La falta de consistencia estructural o la pérdida predictiva falsifica la hipótesis con prelación determinista absoluta sobre futilidad e inconclusión.
   - **FUTILIDAD:** Si no es fracaso (es decir, $\ge 2/4$ folds positivos) y $0 < \Delta R^2_{\mathrm{OOS}}(\mathrm{WF}) < \delta_{\min}$.
   - **INCONCLUSO:** Si no es fracaso ni futilidad (es decir, $\Delta R^2_{\mathrm{OOS}}(\mathrm{WF}) \ge \delta_{\min}$ y $\ge 2/4$ folds positivos), pero no alcanza el estándar de éxito ($p_{\mathrm{DM, FDR}} \ge 0.05$ **O** consistencia frontera de exactamente $2/4$ folds).

| Veredicto | Condiciones Formales Simultáneas (Mutuamente Excluyentes) | Implicación Metodológica |
|---|---|---|
| **ÉXITO** | $\Delta R^2_{\mathrm{OOS}}(\mathrm{WF}) \ge \delta_{\min}$<br>y $p_{\mathrm{DM, FDR}} < 0.05$ (en C1)<br>y $\ge 3/4$ folds con $\Delta R^2 > 0$<br>y en Holdout: $\Delta R^2_{\mathrm{OOS}}(\mathrm{HO}) > 0$ con $p_{\mathrm{DM}}(\mathrm{HO}) < 0.05$. | Evidencia favorable confirmada de que la geometría de liquidez añade señal. Autoriza estudio económico (Fase 7). |
| **DISCREPANCIA HOLDOUT** | $\Delta R^2_{\mathrm{OOS}}(\mathrm{WF}) \ge \delta_{\min}$<br>y $p_{\mathrm{DM, FDR}} < 0.05$ (en C1)<br>y $\ge 3/4$ folds con $\Delta R^2 > 0$<br>pero en Holdout: $\Delta R^2_{\mathrm{OOS}}(\mathrm{HO}) \le 0$ o $p_{\mathrm{DM}}(\mathrm{HO}) \ge 0.05$. | No se acepta H1. Sospecha de sobreajuste o quiebre de régimen temporal. Se congela la investigación. |
| **FRACASO (Falsación)** | $\Delta R^2_{\mathrm{OOS}}(\mathrm{WF}) \le 0$ **O** $< 2/4$ folds positivos ($< 50\%$).<br>*(Prelación determinista sobre Futilidad e Inconclusión).* | Hipótesis H1 rechazada sin ambigüedad. La geometría no mejora el baseline B+++ o es inconsistente temporalmente. Cierre de la línea. |
| **FUTILIDAD** | $0 < \Delta R^2_{\mathrm{OOS}}(\mathrm{WF}) < \delta_{\min}$ **Y** $\ge 2/4$ folds positivos. | Efecto estadístico o residual despreciable para fines prácticos. Cierre definitivo de la línea sin avanzar a V4. |
| **INCONCLUSO** | $\Delta R^2_{\mathrm{OOS}}(\mathrm{WF}) \ge \delta_{\min}$ **Y** $\ge 2/4$ folds positivos,<br>con $p_{\mathrm{DM, FDR}} \ge 0.05$ **O** exactamente $2/4$ folds positivos. | Falta de potencia estadística tras FDR o consistencia frontera (50%). No se declara éxito; se registra como inconcluso sin modificar el test. |

### 8.4 Protocolo Estadístico
1. **Pérdida Agregada Walk-Forward:**
   $$\mathrm{MSE}_{\mathrm{base}} = \frac{1}{|T|} \sum_{t \in T} (y_t - \hat{y}_{t, \mathrm{base}})^2, \quad \mathrm{MSE}_{\mathrm{alt}} = \frac{1}{|T|} \sum_{t \in T} (y_t - \hat{y}_{t, \mathrm{alt}})^2$$
   $$\Delta R^2_{\mathrm{OOS}} = 1 - \frac{\mathrm{MSE}_{\mathrm{alt}}}{\mathrm{MSE}_{\mathrm{base}}}$$
   Calculado sobre el conjunto agregado de observaciones out-of-sample $T = \bigcup_{i=1}^4 T_{\mathrm{test}, i}$.
2. **Diebold-Mariano con Varianza HAC Newey-West:**
   - Serie diferencial: $d_t = e_{t, \mathrm{base}}^2 - e_{t, \mathrm{alt}}^2$.
   - Ancho de banda primario preespecificado: **$L = 20$ lags** ($2H$), justificado por la estructura $\mathrm{MA}(9)$ de los retornos solapados a 10s más la persistencia autorregresiva de las features.
   - Comprobaciones de sensibilidad: se reportan diagnósticos con $L=10$ y $L=40$.
3. **Ajuste Benjamini-Hochberg (FDR):**
   - Control de tasa de falsos descubrimientos al $5\%$ aplicado conjuntamente sobre los contrastes confirmatorios $C1, C2, C3, C4$.
4. **Bootstrap por Bloques Estacionarios:**
   - Procedimiento de Politis & Romano (1994) con longitud media de bloque geométrico $1/p = 15\text{ s}$ ($> H=10\text{ s}$).
   - $B = 1000$ remuestreos deterministas (semilla congelada 42) para intervalo de confianza al $95\%$.

---

## 9. Plan de implementación — fases y entregables

### FASE 0 — Auditoría del estado existente

**Objetivo:** Verificar pipeline V2 intacto antes de modificar nada.

**Tareas:**
1. Ejecutar suite de tests actual; registrar aprobados/fallidos/duración.
2. Verificar `features.py`: NAVIER V0.1 líneas 111–127 intactas.
3. Comprobar hashes de los 11 datasets de sesión.
4. Registrar versiones: Python, numpy, pandas, scipy, pyarrow.

**Entregable:** `docs/v3_audit_phase0.md`  
**Criterio:** Tests pasan (o fallos documentados). Hashes coinciden. V0.1 intacto.

---

### FASE 1 — Implementación de features V3

**Objetivo:** Añadir variables V3 a `features.py` en namespace `v03_`, sin tocar V0.1/V0.2.

**Implementación (en `features.py`):**

```python
# --- NAVIER V3: Liquidity-Conditioned Price Impact (namespace v03_)
# TODAS causales: usan solo información <= t

def _depth_contra(bq, aq, ofi, k):
    """Profundidad del lado que recibe la presión (ask si OFI>0, bid si OFI<0)."""
    d_ask = aq[:, :k].sum(axis=1)
    d_bid = bq[:, :k].sum(axis=1)
    return np.where(ofi >= 0, d_ask, d_bid)

# En compute_features():
ofi_vals = out["ofi_5"].to_numpy()
eps = 1e-6

d_contra_k3 = _depth_contra(bq, aq, ofi_vals, k=3)
d_contra_k5 = _depth_contra(bq, aq, ofi_vals, k=5)

out["v03_pnpc_k3"] = ofi_vals / (d_contra_k3 + eps)
out["v03_pnpc_k5"] = ofi_vals / (d_contra_k5 + eps)

out["v03_liq_conc_ask"] = aq[:, 0] / (aq.sum(axis=1) + eps)
out["v03_liq_conc_bid"] = bq[:, 0] / (bq.sum(axis=1) + eps)

liq_conc_contra = np.where(ofi_vals >= 0,
                            out["v03_liq_conc_ask"].to_numpy(),
                            out["v03_liq_conc_bid"].to_numpy())
out["v03_impact_conc_k3"] = out["v03_pnpc_k3"].to_numpy() * liq_conc_contra

# Exploratorio H1a: reposición (τ=5 s)
d_ask_k3 = aq[:, :3].sum(axis=1)
d_bid_k3 = bq[:, :3].sum(axis=1)
d_ask_mean60 = pd.Series(d_ask_k3).rolling(60).mean().to_numpy()
d_bid_mean60 = pd.Series(d_bid_k3).rolling(60).mean().to_numpy()
out["v03_depth_replenish_ask"] = (
    pd.Series(d_ask_k3).diff(5).to_numpy() / (d_ask_mean60 + eps)
)
out["v03_depth_replenish_bid"] = (
    pd.Series(d_bid_k3).diff(5).to_numpy() / (d_bid_mean60 + eps)
)

# Invalidar reposición si hay gap en los últimos 5 s
if "state_source" in raw.columns:
    gap5 = (raw["state_source"] == "GAP_DISCONTINUITY").rolling(5, min_periods=1).max() == 1
    out.loc[gap5, ["v03_depth_replenish_ask", "v03_depth_replenish_bid"]] = np.nan
```

**Tests requeridos en `tests/test_features_v3.py`:**
1. Causalidad: `v03_pnpc_k3` en fila `t` usa solo datos de filas ≤ `t`.
2. Signo correcto: OFI > 0 → denominador es ask; OFI < 0 → denominador es bid.
3. Singularidad: `depth_contra = 0` → resultado finito (no inf).
4. GAP mask: filas con discontinuidad en últimos 5 s → `v03_depth_replenish_*` = NaN.
5. Idempotencia: procesar en chunks produce el mismo resultado que en bloque.
6. V0.1 invariante: los valores de `u`, `dI_dt`, `grad_*`, `curv_*`, `re_log` no cambian.

**Entregable:** `features.py` actualizado + `tests/test_features_v3.py` (todos los tests pasan).

---

### FASE 2 — Actualización del motor de evaluación y congelación

**Objetivo:** Añadir B++ y Modelo E al script de evaluación; congelar el protocolo.

**En `evaluate_models_oos.py`:**

```python
# Interacciones B++ (calculadas en ajuste, no pre-computadas)
def add_bplusplus_interactions(X_df, cols):
    """Añade ofi_5*imb_full y ofi_5*(-depth_log) como columnas extra."""
    X = X_df[cols].copy()
    X["_ofi_x_imb"] = X_df["ofi_5"] * X_df["imb_full"]
    X["_ofi_x_invdepth"] = X_df["ofi_5"] * (-X_df["depth_log"])
    return X.to_numpy(float)

MODEL_SPECS_V3 = {
    "Model_B":      lambda df: df[MODEL_B].to_numpy(float),
    "Model_Bplus":  lambda df: df[MODEL_BPLUS].to_numpy(float),
    "Model_Bplusplus": lambda df: add_bplusplus_interactions(df, MODEL_BPLUS),
    "Model_E":      lambda df: add_bplusplus_interactions(df, MODEL_BPLUS + NAVIER_V3_CORE),
    "Model_E_H1a":  lambda df: add_bplusplus_interactions(df, MODEL_BPLUS + NAVIER_V3_CORE + NAVIER_V3_REPLENISH),
}

CONFIRMATORY_PAIRS_V3 = [
    ("Model_E", "Model_Bplusplus"),   # C1 — principal
    ("Model_E", "Model_Bplus"),       # C2 — comparabilidad V2
    ("Model_E", "Model_B"),           # C3 — referencia histórica
]
EXPLORATORY_PAIRS_V3 = [
    ("Model_E_H1a", "Model_E"),       # C4 — reposición
]
```

**Congelación:** Una vez que comienza la captura (Fase 3), `NAVIER_V3_PROTOCOL.md` y las especificaciones de las secciones 2–8 quedan bloqueadas. Los cambios posteriores van a la sección 11.

**Entregable:** `scripts/evaluate_models_oos_v3.py` + `docs/v3_freeze_manifest.md` (hash del protocolo y del código de evaluación en el momento de congelación).

---

### FASE 3 — Captura del bloque de validación independiente

**Objetivo:** Datos no contaminados.

**Protocolo:**
- Mismo capturador y configuración que sesiones 1–11.
- ≥ 9 sesiones, ~40 min, franjas horarias variadas (incluir al menos 2 en horario europeo y 2 en horario americano).
- Almacenamiento en `data/v3_validation/` con manifiesto de hashes.
- El investigador que diseñó features V3 **no consulta residuos** en estos datos hasta Fase 5.
- Se aplica resampler 001.9 con mismos criterios de calidad que V2.

**Entregable:** `docs/v3_capture_manifest.md` (hashes, fechas, franjas, métricas de calidad por sesión).

**Criterio:** ≥ 6 500 observaciones limpias (sin gap_future, σ̂₆₀ ≥ 0.01 bps).

---

### FASE 4 — Construcción del dataset V3

**Objetivo:** Generar parquet con features completas sobre datos de validación.

**Pasos:**
1. Ejecutar pipeline con features V3 sobre `data/v3_validation/`.
2. Verificar cobertura ≥ 95% en variables V3.
3. Estadísticas descriptivas de NAVIER_V3_CORE + diagnóstico de colinealidad.
4. Correlación de `v03_pnpc_k3` con `ofi_5`, `imb_full`, `depth_log` (si |corr| > 0.95, reportar antes de ajustar).
5. VIF de NAVIER_V3_CORE dentro de B++ (si VIF > 20, documentar).
6. **No ajustar modelos predictivos en este paso.**

**Entregable:** `data/research_dataset_v3.parquet` + `docs/v3_features_audit.md`.

---

### FASE 5 — Evaluación predictiva fuera de muestra

**Objetivo:** Comparación confirmatory de H1 sobre bloque de validación.

**Parámetros walk-forward:** k=5, purge=10, embargo=10, holdout=20% — idénticos a V2.

**Orden de análisis:**
1. Ajustar y evaluar todos los modelos (B, B+, B++, E, E_H1a).
2. Calcular ΔR²_OOS y tests DM para comparaciones confirmatorias C1–C3.
3. Aplicar FDR sobre los tres p-valores confirmatorios.
4. Calcular IC por bootstrap de bloques.
5. Evaluar consistencia por fold.
6. Evaluar sobre hold-out final.
7. Aplicar criterios de aceptación/fracaso/inconclusión preespecificados.
8. Calcular C4 (exploratorio) y etiquetarlo como tal.

**Entregable:** `results/oos_model_evaluation_v3.json` con estructura análoga a V2.

---

### FASE 6 — Interpretación y decisión

**Objetivo:** Aplicar criterios preespecificados. No post-hoc.

**Prohibido:**
- Cambiar la métrica primaria.
- Excluir sesiones que empeoran el resultado.
- Elevar C4 a confirmatorio.
- Añadir nuevas variables V3 después de ver residuos del hold-out.

**Entregable:** `docs/v3_final_verdict.md` con veredicto, criterios cumplidos/no, y decisión binaria sobre Fase 7.

---

### FASE 7 — Evaluación económica (solo si H1 aceptada en Fase 6)

- Spread de entrada/salida (spread observado en dataset V3).
- Comisiones Kraken spot aplicables.
- Deslizamiento estimado por tamaño de posición.
- Latencia: ≥ 50 ms de procesamiento desde observación.
- No declarar rentabilidad sin cerrar esta fase.

---

## 10. Organización de archivos

```
navier_lab_project/
├── NAVIER_V3_PROTOCOL.md              ← Este documento (congelado)
├── navier_lab/
│   ├── features.py                    ← v03_* añadidos; V0.1/V0.2 intactos
│   └── schema.py                      ← Sin cambios
├── scripts/
│   ├── evaluate_models_oos_v3.py      ← Motor de evaluación V3
│   └── build_research_dataset.py      ← Sin cambios en lógica
├── tests/
│   └── test_features_v3.py            ← Tests unitarios V3
├── data/
│   └── v3_validation/                 ← Bloque independiente (cerrado hasta Fase 4)
├── docs/
│   ├── v3_audit_phase0.md
│   ├── v3_capture_manifest.md
│   ├── v3_features_audit.md
│   ├── v3_evaluation_report.md
│   └── v3_final_verdict.md
└── results/
    └── oos_model_evaluation_v3.json
```

**Reglas:**
- Sesiones 1–11 y sus resultados NO se modifican.
- Scripts nuevos llevan sufijo `_v3`.
- `research_dataset_v2.parquet` y `oos_model_evaluation_sessions*.json` son solo lectura.

---

## 11. Lo que V3 no es

- **V3 no prueba que el mercado sea un fluido.** Prueba si una variable empírica de microestructura (razón presión/resistencia) predice mejor que el mejor baseline convencional disponible.
- **V3 no reemplaza V0.1.** Las fórmulas de V0.1 quedan intactas como referencia histórica.
- **Si V3 tampoco mejora B++**, no habrá razón para creer que variantes adicionales de la misma familia lo harían con los mismos datos.
- **V3 no es rentable por hipótesis.** La evaluación económica solo tiene sentido si H1 se acepta en Fase 6.
- **V3 no usa redes neuronales.** La complejidad del modelo debe justificarse por la hipótesis, no por la disponibilidad de la arquitectura.

---

## 12. Registro de desviaciones

*(Completar aquí cualquier cambio posterior a la congelación, con fecha, justificación y efecto en la interpretación)*

| Fecha | Sección afectada | Descripción del cambio | Motivo | Firmado por |
|---|---|---|---|---|
| 2026-10-22 | Secciones 4 y 8.3 | 1. Corrección dimensional de la interacción en B++: sustitución de `ofi_5 / (exp(depth_log) + ε)` por `ofi_raw_5 / (exp(depth_log) + ε)` (adimensional, $[BTC]/[BTC]=1$).<br>2. Matriz de decisión MECE: establecimiento de jerarquía determinista estricta para resolver solapamientos previos entre fracaso/inconclusión y fracaso/futilidad cuando $\text{folds} < 2/4$. | Cierre formal de dos observaciones críticas de auditoría previa a la captura independiente de datos. No altera umbrales preespecificados ($\delta_{\min}=0.0010$, $\alpha=0.05$). | Auditor Cuantitativo / NAVIER Lab |
| 2026-10-23 | Sección 3 (Diseño experimental) | Reducción del número de sesiones de captura de **9 a 7** por decisión operativa del investigador principal. El protocolo preregistraba un mínimo de 9 sesiones. | Interrupción operativa durante la captura de la sesión 8 (denegación de permiso de ejecución). Las 7 sesiones completadas producen **15 762 observaciones 1s limpias** — 2.42× el mínimo requerido de 6 500. No hubo acceso a resultados predictivos previo a esta decisión. La reducción no compromete el requisito de potencia mínima. Sesiones cubren 2026-10-22 a 2026-10-23, ventanas horarias variadas (16:58–18:54 UTC día 1; 14:46–18:54 UTC día 2). | Investigador Principal / NAVIER Lab |

---

*Fin del protocolo. Congelar antes de abrir los datos de validación independiente (Fase 3).*
