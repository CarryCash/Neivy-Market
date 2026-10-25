# NAVIER V2 — Protocolo Experimental y Documento de Preespecificación

**Versión:** 2.0.0-FROZEN  
**Fecha de congelamiento:** 19 de octubre de 2026  
**Responsable:** Ingeniero Cuantitativo Sénior y Responsable de Reproducibilidad Científica  
**Estado:** DOCUMENTO CONGELADO Y VERSIONADO (FASE 2)

---

## 1. Declaración de Misión y Filosofía Epistemológica

El objetivo del proyecto **NAVIER V2** es investigar formalmente la siguiente pregunta científica:

> **¿Las variables inspiradas en dinámica de fluidos (velocidad de log-mid $u$, derivada del imbalance $\frac{dI}{dt}$, gradiente y curvatura espacial de liquidez $\nabla V, \nabla^2 V$, y proxy de número de Reynolds $Re_m$) aportan información predictiva incremental, estable y medible sobre el movimiento del mid-price de Bitcoin a corto plazo, frente a un modelo convencional sólido de microestructura L2?**

### Regla Epistemológica
No se asume que la hipótesis sea correcta. Los tres resultados posibles son científicamente válidos:
- **Positivo:** Evidencia de mejora predictiva fuera de muestra ($\Delta R^2_{\text{OOS}} > 0$, $p < 0.05$ robusto a autocorrelación) y estable ante controles de dinámica lineal (Modelo B+).
- **Negativo:** Ausencia de poder predictivo incremental o absorción total de la señal por variables convencionales y sus rezagos.
- **Inconcluso:** Resultados erráticos entre regímenes, inestables entre sesiones o dependientes del método de estimación.

---

## 2. Par, Venue y Canal Seleccionados

1. **Exchange:** Kraken Spot WebSocket API v2 (`wss://ws.kraken.com/v2`).
2. **Canal:** `book` público (modo solo datos de mercado, sin órdenes ni credenciales).
3. **Par seleccionado:** **`BTC/USD`**.
4. **Justificación empírica:** Ensayo piloto simultáneo de 15 minutos (Fase 1):
   - Continuidad temporal superior: **98.78 %** de segundos observados vs 91.65 % en BTC/USDT.
   - Profundidad nominal 10 niveles: **$961 098 USD** vs $177 442 USDT ($5.4\times$ mayor liquidez).
   - Menor antigüedad de libro (*staleness*): $83.6\text{ ms}$ mediana vs $113.3\text{ ms}$.
   - Spread ultra-ajustado y eficiente: clavado en el tick mínimo ($0.10$ USD $\approx 0.0122\text{ bps}$).

---

## 3. Resolución Espaciotemporal y Mecanismo de Resampleo

1. **Profundidad espacial:** $K = 10$ niveles por lado (`bid_px_1..10`, `bid_qty_1..10`, `ask_px_1..10`, `ask_qty_1..10`).
2. **Rejilla temporal:** Intervalos regulares de **$1.0\text{ segundo}$**.
3. **Regla de causalidad estricta:**
   - Intervalo semiabierto a la izquierda y cerrado a la derecha:
     $$\tau \in (T - 1.0\text{ s}, T]$$
   - El registro resultante se rotula con la cota superior $T$. Ningún evento posterior a $T$ interviene en el cálculo del estado en $T$.
4. **Desempate determinista ($\Delta t = 0$):** En ráfagas de alta frecuencia con idéntico timestamp de exchange, prevalece el último mensaje procesado según el orden unívoco de llegada (`_source_row_id`).
5. **Umbral de gap:** $\Delta t_{\text{gap}} = 3.0\text{ segundos}$. Si transcurren más de $3\text{ s}$ sin mensajes, el estado se tipifica como `GAP_DISCONTINUITY` y se anulan los niveles de libro para evitar interpolación espuria.

---

## 4. Diseño del Muestreo Multisesión (Fase 3)

1. **Diversidad temporal:** Capturas distribuidas en franjas horarias no redundantes para muestrear volatilidad variable:
   - Sesión A: Horario europeo / apertura Londres (08:00 - 12:00 UTC).
   - Sesión B: Solapamiento Londres / Nueva York (13:00 - 17:00 UTC).
   - Sesión C: Tarde americana / apertura Asia (20:00 - 00:00 UTC).
2. **Volumen muestral mínimo:** Acumular un mínimo de **$10 800\text{ segundos}$** (3 horas totales) de datos resampleados válidos tras descartar periodos de calentamiento y gaps.
3. **Trazabilidad:** Cada sesión contará con su manifiesto `.manifest.json`, hash SHA-256 de entrada y salida, timestamps de exchange y recepción, y conteo de estados.

---

## 5. Criterios de Calidad, Discontinuidad y Exclusión de Datos

Cada segundo $T$ en el dataset resampleado se clasifica mediante la variable `state_source`:

1. `STATE_OBSERVED` ($1$): Al menos un mensaje procesado en $(T - 1\text{ s}, T]$.
2. `STATE_CARRIED_FORWARD` ($2$): Cero mensajes en el segundo actual, pero tiempo transcurrido desde el último mensaje $\le 3.0\text{ s}$. Se conserva el libro por persistencia temporal de liquidez.
3. `STATE_GAP_DISCONTINUITY` ($3$): Silencio $> 3.0\text{ s}$ o pérdida de sincronización. Todos los niveles se fijan en `NaN`.

### Reglas de Exclusión Operativa:
- **Calentamiento (*burn-in*):** Las primeras 60 observaciones de cada sesión se descartan (requeridas para el cálculo causal de la volatilidad realizada $vol60$).
- **Contaminación histórica:** Si en los últimos $60\text{ s}$ existe algún `GAP_DISCONTINUITY` o el porcentaje de filas arrastradas supera el $20\text{ \%}$, las derivadas dinámicas ($u, \frac{dI}{dt}, Re_m$) se marcan como `NaN`.
- **Contaminación futura en la etiqueta:** Si en el intervalo $[t, t + H]$ ocurre una discontinuidad o la antigüedad del libro en $t + H$ supera los $1000\text{ ms}$, la etiqueta objetivo $y_t$ se excluye (`NaN`).

---

## 6. Variables de Entrada y Especificación Matemática

### A. Variables Básicas (Descriptivas)
- Mid-price: $mid_t = \frac{ask\_px\_1 + bid\_px\_1}{2}$
- Spread nominal y relativo: $spread\_bps_t = \frac{ask\_px\_1 - bid\_px\_1}{mid_t} \times 10^4$
- Profundidad logarítmica: $depth\_log_t = \ln(V_b + V_a)$, con $V_b = \sum_{k=1}^{10} q_{b,k}$, $V_a = \sum_{k=1}^{10} q_{a,k}$.
- Volatilidad realizada (60 s): $vol60\_bps_t = \text{std}(\Delta \ln(mid) \times 10^4)$ en ventana $[t-59, t]$.

### B. Variables Tradicionales de Microestructura (Modelo B)
- Imbalance total: $imb\_full_t = \frac{V_b - V_a}{V_b + V_a} \in [-1, 1]$
- Imbalance en el BBO: $imb\_top1_t = \frac{q_{b,1} - q_{a,1}}{q_{b,1} + q_{a,1}} \in [-1, 1]$
- Order Flow Imbalance (OFI Cont-Kukanov-Stoikov a 5 s):
  $$e_t = I_{\{p_b \ge p_b^0\}} q_b - I_{\{p_b \le p_b^0\}} q_b^0 - I_{\{p_a \le p_a^0\}} q_a + I_{\{p_a \ge p_a^0\}} q_a^0$$
  $$ofi\_5_t = \frac{\sum_{i=0}^4 e_{t-i}}{\text{mean}_{60}(q_{b,1} + q_{a,1})}$$
- Momentum / Retornos pasados: $ret\_1 = \ln\left(\frac{mid_t}{mid_{t-1}}\right) \times 10^4$, $ret\_5 = \ln\left(\frac{mid_t}{mid_{t-5}}\right) \times 10^4$, $ret\_30 = \ln\left(\frac{mid_t}{mid_{t-30}}\right) \times 10^4$.

### C. Rezagos Temporales de Imbalance (Modelo B+)
- Controles autorregresivos lineales: $imb\_full\_lag2$, $imb\_full\_lag5$, $imb\_full\_lag8$.

### D. Variables NAVIER V0.1 (Inmutables — Línea Base Científica)
- **Velocidad de precio $u_t$:** Pendiente MCO de $\ln(mid) \times 10^4$ sobre los últimos 5 segundos ($w=5$). Unidades: $\text{bps/s}$.
- **Derivada temporal del imbalance:** $\frac{dI}{dt} = \frac{I_{\text{smooth}}(t) - I_{\text{smooth}}(t-5)}{5}$, donde $I_{\text{smooth}}$ es la media móvil de 3 s de $imb\_full$.
- **Gradiente y curvatura espacial por lado:**
  Sea $norm = \frac{1}{20}\sum_{k=1}^{10}(q_{b,k} + q_{a,k})$. Se normaliza $b_{n,k} = \frac{q_{b,k}}{norm}$, $a_{n,k} = \frac{q_{a,k}}{norm}$.
  $$grad\_bid = \sum_{k=1}^{10} b_{n,k} w_k^{\text{slope}}, \quad grad\_ask = \sum_{k=1}^{10} a_{n,k} w_k^{\text{slope}}$$
  $$curv\_bid = \sum_{k=1}^{10} b_{n,k} w_k^{\text{curv}}, \quad curv\_ask = \sum_{k=1}^{10} a_{n,k} w_k^{\text{curv}}$$
  donde $w^{\text{slope}}$ y $w^{\text{curv}}$ son proyectores ortogonales centrados sobre $k \in \{1..10\}$.
- **Proxy de Número de Reynolds ($Re_m$):**
  $$L_{\text{bps}} = \frac{ask\_px\_10 - bid\_px\_10}{mid_t} \times 10^4, \quad D_t = (vol60\_bps_t)^2$$
  $$Re_m = \frac{|u_t| \cdot \max(0, L_{\text{bps}})}{D_t}, \quad re\_log = \ln(1 + Re_m)$$

### E. Variantes Experimentales NAVIER V0.2 (Espacio Separado — Modelo D)
- $v02\_l\_vwap\_bps$: Distancia media de órdenes al mid ponderada por volumen en puntos básicos:
  $$l_{\text{bid}} = \frac{\sum (mid - bid_k) q_{b,k}}{V_b \cdot mid} \times 10^4, \quad l_{\text{ask}} = \frac{\sum (ask_k - mid) q_{a,k}}{V_a \cdot mid} \times 10^4$$
  $$v02\_l\_vwap\_bps = \frac{l_{\text{bid}} + l_{\text{ask}}}{2}$$
- $v02\_grad\_bid\_norm$, $v02\_grad\_ask\_norm$: Normalización intra-lado ($b_k / V_b$, $a_k / V_a$) para desacoplar el imbalance de la forma geométrica del libro.
- $v02\_re\_log\_reg$: Reynolds regularizado con cota mínima de volatilidad $\epsilon = 0.05\text{ bps}$ ($D_{\text{reg}} = \max(D, \epsilon^2)$) y escala $L_{\text{vwap}}$.

---

## 7. Definición del Objetivo y Horizontes de Predicción

1. **Horizonte Primario:** **$H = 10\text{ segundos}$** (fijo e inalterable).
2. **Horizontes Secundarios (Estrictamente Exploratorios):** $H = 5\text{ s}$ y $H = 30\text{ s}$.
3. **Definición del Objetivo Nominal:**
   $$y\_bps_t = \ln\left(\frac{mid_{t+10}}{mid_t}\right) \times 10^4 \quad (\text{en puntos básicos})$$
4. **Definición del Objetivo Primario Estandarizado:**
   $$y_t = \frac{y\_bps_t}{vol60\_bps_t \cdot \sqrt{10}}$$
   Condicionado causalmente a $vol60\_bps_t \ge 0.01\text{ bps}$.

---

## 8. Familias de Modelos y Comparativa Anidada

| Modelo | Conjunto de Variables | Rol Teórico |
|---|---|---|
| **Modelo A** | `spread_bps`, `depth_log`, `vol60_bps` | Línea base pasiva de libro. |
| **Modelo B** | Modelo A + `imb_full`, `imb_top1`, `ofi_5`, `ret_1`, `ret_5`, `ret_30` | Microestructura convencional sólida. |
| **Modelo B+** | Modelo B + `imb_full_lag2`, `imb_full_lag5`, `imb_full_lag8` | Microestructura + control autorregresivo lineal de flujo. |
| **Modelo C** | Modelo B + NAVIER V0.1 (`u`, `dI_dt`, `grad_bid`, `grad_ask`, `curv_bid`, `curv_ask`, `re_log`) | Hipótesis central NAVIER V0.1. |
| **Modelo D** | Modelo B + NAVIER V0.2 (`u`, `dI_dt`, `v02_grad_bid_norm`, `v02_grad_ask_norm`, `v02_re_log_reg`) | Hipótesis regularizada NAVIER V0.2. |

### Contraste Clave:
El test crucial no es si C supera a A, sino si **C mejora incrementalmente a B y resiste ante B+**.

---

## 9. Protocolo de Validación Fuera de Muestra y Purgado

1. **Evaluación cronológica Walk-Forward:** Partición temporal secuencial con entrenamiento en el pasado y evaluación en el futuro inmediato:
   - Pliegue $k$: Entrenamiento en $[T_{0,k}, T_{1,k}]$, Test en $[T_{1,k} + E, T_{2,k}]$.
2. **Purgado (*Purging*):** Se descartan del conjunto de entrenamiento los últimos $H=10$ segundos previos a $T_{1,k}$ para evitar solapamiento entre la etiqueta futura del final del entrenamiento y el inicio del test.
3. **Embargo temporal:** $E = 10\text{ segundos}$ entre el final del entrenamiento y el inicio del test.
4. **Hermeticidad muestral:** Normalizaciones (z-scores), medias y desviaciones típicas se calculan exclusivamente sobre el bloque de entrenamiento de cada pliegue y se aplican congeladas al bloque de test.
5. **Hold-out final intocable:** El último **20 % temporal** del dataset multisesión final queda completamente reservado e inaccesible hasta la congelación final de todos los modelos.

---

## 10. Métrica Primaria, Pruebas Estadísticas y Criterios de Éxito

### A. Métrica Primaria
Coeficiente de determinación fuera de muestra pareado ($\Delta R^2_{\text{OOS}}$):
$$\Delta R^2_{\text{OOS}}(C \text{ vs } B) = 1 - \frac{\sum_{t \in \text{Test}} (y_t - \hat{y}_{t, C})^2}{\sum_{t \in \text{Test}} (y_t - \hat{y}_{t, B})^2}$$

### B. Pruebas de Significación Estadística
1. **Test de Diebold-Mariano (1995) / West (1996):**
   Sobre la serie de diferencias de pérdidas cuadráticas $d_t = e_{B, t}^2 - e_{C, t}^2$, utilizando un estimador robusto de varianza HAC (Newey-West) con rezago dependiente de $H=10$:
   $$DM = \frac{\bar{d}}{\sqrt{\hat{\Omega}_{\text{HAC}} / N}} \sim \mathcal{N}(0, 1)$$
2. **Ajuste por Comparaciones Múltiples:** Corrección de Benjamini-Hochberg (FDR) con tasa de falso descubrimiento controlada al $5\text{ \%}$ ($\alpha = 0.05$).
3. **Estabilidad temporal:** Cálculo de $\Delta R^2_{\text{OOS}}$ desglosado por sesión individual.

### C. Criterios de Interpretación Formal
- **Éxito (Confirmación de hipótesis):** $\Delta R^2_{\text{OOS}} > 0$ con significancia estadística $p < 0.05$ (Diebold-Mariano HAC corregido por FDR) tanto frente al Modelo B como frente al Modelo B+, y con $\Delta R^2 > 0$ en al menos el 70 % de las sesiones independientes y en el hold-out final.
- **Fracaso (Rechazo de hipótesis):** $\Delta R^2_{\text{OOS}} \le 0$, o valor $p \ge 0.05$, o si la aparente ventaja de C frente a B desaparece frente a B+ (señal explicada por colinealidad con rezagos de imbalance tradicionales).
- **Inconcluso:** $\Delta R^2_{\text{OOS}} > 0$ en promedio pero concentrado en una única sesión atípica, o no reproducible en el hold-out final.

---

## 11. Política de Discontinuidad, Fallos e Invalidez de Sesiones

Una sesión de captura se considerará **inválida para la muestra principal** si:
1. Sufre desconexión no recuperada en $< 30\text{ segundos}$ o más de 2 desconexiones en la misma sesión.
2. Registra fallos de checksum CRC32 en mensajes de WebSocket.
3. El porcentaje de segundos en `GAP_DISCONTINUITY` supera el $3.0\text{ \%}$ del total de la sesión.
4. Tras aplicar los filtros de calidad, la cantidad de segundos utilizables resulta inferior a $1500\text{ s}$ ($25\text{ min}$).

---

## 12. Blindaje contra Selección Retrospectiva (*Data Snooping*)

1. **Uso exclusivo del piloto de la Fase 1:** La captura piloto de 15 minutos (`pilot_btc_usd_l2.parquet` y `pilot_btc_usdt_l2.parquet`) se usó exclusivamente para verificar la conectividad de WebSocket, validar los checksums y comparar la densidad de microestructura. **Queda expresamente prohibido incluirla en el conjunto de entrenamiento, validación o prueba de la Fase 5.**
2. **Congelamiento de código:** Las fórmulas y la definición de features quedan congeladas en esta versión 2.0.0. No se calibrarán umbrales ni se añadirán variables a posteriori tras observar los $R^2$ predictivos.
3. **Registro de Desviaciones:** Cualquier alteración técnica imprevista durante la captura de la Fase 3 deberá quedar documentada en un anexo fechado indicando el motivo de ingeniería.
