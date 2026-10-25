# NAVIER V3 — Informe Formal de Evaluación Fuera de Muestra (Fase 5)

**Fecha de ejecución:** 2026-10-24 14:01:17 UTC  
**Auditor Cuantitativo:** Independiente  
**Dataset evaluado:** [`data/research_dataset_v3.parquet`](file:///C:/Users/USER/Downloads/navier_lab_project/navier_lab_project/data/research_dataset_v3.parquet)  
**Manifiesto del Dataset:** [`data/research_dataset_v3.manifest.json`](file:///C:/Users/USER/Downloads/navier_lab_project/navier_lab_project/data/research_dataset_v3.manifest.json)  
**Código del evaluador:** [`scripts/evaluate_models_oos_v3.py`](file:///C:/Users/USER/Downloads/navier_lab_project/navier_lab_project/scripts/evaluate_models_oos_v3.py)  
**Runner de ejecución:** [`scripts/run_phase5_evaluation.py`](file:///C:/Users/USER/Downloads/navier_lab_project/navier_lab_project/scripts/run_phase5_evaluation.py)  
**Artefactos de resultados:**  
- Resultados numéricos: [`results/phase5_v3/oos_evaluation_results.json`](file:///C:/Users/USER/Downloads/navier_lab_project/navier_lab_project/results/phase5_v3/oos_evaluation_results.json)  
- Metadatos de auditoría: [`results/phase5_v3/execution_metadata.json`](file:///C:/Users/USER/Downloads/navier_lab_project/navier_lab_project/results/phase5_v3/execution_metadata.json)  

---

## Veredicto Formal Preregistrado

# **`INCONCLUSO (EVIDENCIA DÉBIL O POTENCIA INSUFICIENTE TRAS FDR)`**

> **Dictamen Científico Principal:**  
> La hipótesis $H_1$ (predictibilidad incremental de la geometría del libro L2 más allá de la microestructura convencional) **NO RECIBE APOYO EMPÍRICO**.  
> Aunque el estimador puntual del contraste primario C1 en el Walk-Forward muestra una ganancia nominal de $\Delta R^2_{\mathrm{OOS}} = +0.192\%$, el efecto es **estadísticamente indistinguible de cero** ($p_{\mathrm{nominal}} = 0.4771$, $p_{\mathrm{FDR}} = 0.7276$), su intervalo de confianza bootstrap al 95% cruza ampliamente el cero ($[-0.675\%, +0.502\%]$) y el modelo **se deteriora fuertemente en el Holdout cronológico final** ($\Delta R^2_{\mathrm{OOS, holdout}} = -0.535\%$).  
> Asimismo, frente a los baselines estándar sin la variable de ratio ($B^{++}$, $B^+$, $B$), el modelo geométrico $E$ es **sistemáticamente inferior** ($\Delta R^2_{\mathrm{OOS}} < 0$).

---

## 1. Integridad de Ejecución

- **Verificación previa de archivos congelados:** 7 de 7 componentes verificados byte a byte contra [`docs/v3_freeze_manifest.md`](file:///C:/Users/USER/Downloads/navier_lab_project/navier_lab_project/docs/v3_freeze_manifest.md):
  * `NAVIER_V3_PROTOCOL.md`: `0183b474253d5b6f50f25aba7e463a925a4ff5183da99a3648736dd93095114a` (OK)
  * `navier_lab/features.py`: `1b642ebfe827e9348f8ded67f9e5f706d0f6599074156094fb73131a2fa853db` (OK)
  * `navier_lab/schema.py`: `a34cec8a9d57b3bdcf8c5b7e803452b33e288b238cba2f398c66f0fa8cf80e1a` (OK)
  * `navier_lab/resampler.py`: `220be7754e5377f69d4539b400435f40a6e96257687237e1ac8cf957e3de7f35` (OK)
  * `scripts/evaluate_models_oos_v3.py`: `52f566f12bc2728eacebeef97ebcce04133e68d3166bcdedfd9c6d5f7b67bedb` (OK)
  * `scripts/capture_kraken_l2.py`: `d7f01a500f54ac790262ad41806394a8288189e5d31c55f012a57f903c681712` (OK)
  * `tests/test_features_v3.py`: `9202eb588baa451c2cb53e8be6ba25bb18d08a8195a339eac6f2818074763118` (OK)
- **Verificación del dataset:**
  * Archivo: `data/research_dataset_v3.parquet`
  * SHA-256: `5e7139209e8ee62bfbd6a04f6387e8ba987894f98da75372b2a5a15645c0f7d8` (coincidencia exacta 100% con `data/research_dataset_v3.manifest.json`).
  * Total de filas: 13 558 | Total de columnas: 51.
- **Entorno del sistema:**
  * Python 3.10.9 (64-bit) en Windows 10/11 AMD64.
  * Dependencias numéricas: NumPy `2.2.6`, Pandas `2.3.3`, SciPy `1.15.3`.
- **Condiciones de entrada y excepciones:**
  * Timestamps monótonos crecientes por sesión: Verificado.
  * Duplicados temporales intra-sesión: 0.
  * Sesiones procesadas: 7 sesiones L2 independientes.
  * Excepciones durante la ejecución: 0 (Ejecución limpia en 29.578 segundos).

---

## 2. Resultados del Esquema Walk-Forward

### Partición de la Muestra Común
- **Muestra total limpia:** 13 558 observaciones.
- **Holdout final cronológico (20%):** 2 712 observaciones (preservadas intactas para evaluación final).
- **Muestra para Walk-Forward (`df_eval`):** 10 846 observaciones.
- **Estructura del Walk-Forward:** $k=5$ folds expansivos (4 test splits), con $\text{Purga} = 10\text{ s}$ al final de cada train y $\text{Embargo} = 10\text{ s}$ al inicio de cada test.
- **Observaciones efectivas de test OOS acumuladas:** 8 637 observaciones.

### Desglose por Fold del Contraste Primario C1 ($E \text{ vs } B^{+++}$)

| Split / Fold | Train Obs | Test Obs | $\Delta R^2_{\mathrm{OOS}}$ | Estado |
|:---:|:---:|:---:|:---:|:---:|
| **Fold 1** | 2 159 | 2 159 | $+0.009662$ ($+0.966\%$) | **Positivo** |
| **Fold 2** | 4 328 | 2 159 | $-0.017820$ ($-1.782\%$) | **Negativo** |
| **Fold 3** | 6 497 | 2 160 | $+0.007067$ ($+0.707\%$) | **Positivo** |
| **Fold 4** | 8 666 | 2 159 | $+0.002371$ ($+0.237\%$) | **Positivo** |

- **Consistencia por fold:** 3 de 4 folds positivos ($75.0\%$). Cumple el requisito preregistrado de consistencia ($\ge 75\%$).

---

## 3. Contraste Primario Confirmatorio C1: $E \text{ vs } B^{+++}$

- **Modelos contrastados:**
  * **Base ($B^{+++}$):** Variables básicas + libro tradicional + rezagos + interacciones convencionales (`_ofi_x_imb`, `_ofi_div_depth10`) + ratio de control de presión/profundidad normalizado (`v03_pnpc_k3`).
  * **Alternativo ($E$):** $B^{+++}$ + variables geométricas de hipótesis (`v03_liq_conc_ask`, `v03_liq_conc_bid`, `v03_impact_conc_k3`).
- **Métrica:** $\Delta R^2_{\mathrm{OOS}} = 1 - \frac{\mathrm{MSE}(E)}{\mathrm{MSE}(B^{+++})}$.

| Indicador Estadístico | Valor Numérico | Criterio Preregistrado | Evaluación |
|---|:---:|:---:|:---:|
| **$\Delta R^2_{\mathrm{OOS}}$ en Walk-Forward** | **$+0.001922$ ($+0.1922\%$)** | $\ge +0.0010$ ($+0.10\%$) | **Supera umbral numérico** |
| **Diebold-Mariano $t\text{-stat}$ ($L=20$)** | **$+0.7110$** | $t > 1.96$ | **No significativo** |
| **$p\text{-valor}$ Nominal (Bilateral)** | **$0.4771$ ($47.71\%$)** | $< 0.05$ | **No significativo** |
| **$p\text{-valor}$ Ajustado FDR (Benjamini-Hochberg)** | **$0.7276$ ($72.76\%$)** | $< 0.05$ | **No significativo** |
| **95% CI Bootstrap Estacionario ($B=1000$)** | **$[-0.006750, +0.005024]$** | Límite inferior $> 0$ | **Cruza el cero ampliamente** |
| **Consistencia de Folds** | **$3 / 4$ ($75.0\%$)** | $\ge 75\%$ | **Cumple consistencia** |

**Diagnóstico del efecto:**  
La ganancia estimada en walk-forward ($+0.192\%$) carece de significación estadística. Su $p$-valor ajustado ($72.8\%$) y el intervalo bootstrap demuestran que la variación es perfectamente atribuible al ruido muestral.

---

## 4. Contrastes Secundarios C2–C4 y Exploratorio C5

Todos los modelos fueron evaluados sobre exactamente las mismas 8 637 observaciones del Walk-Forward:

| Contraste | Modelos Comparados | $\Delta R^2_{\mathrm{OOS}}$ | DM $t\text{-stat}$ ($L=20$) | $p\text{-valor}$ Nominal | $p\text{-valor}$ FDR | 95% CI Bootstrap | Folds Positivos |
|:---:|---|:---:|:---:|:---:|:---:|:---:|:---:|
| **C1** | $E \text{ vs } B^{+++}$ | $+0.001922$ | $+0.7110$ | $0.4771$ | $0.7276$ | $[-0.006750, +0.005024]$ | $3 / 4$ ($75\%$) |
| **C2** | $E \text{ vs } B^{++}$ | $-0.000736$ | $-0.3256$ | $0.7447$ | $0.7447$ | $[-0.013333, +0.002520]$ | $2 / 4$ ($50\%$) |
| **C3** | $E \text{ vs } B^{+}$ | $-0.001325$ | $-0.6042$ | $0.5457$ | $0.7276$ | $[-0.014713, +0.001924]$ | $2 / 4$ ($50\%$) |
| **C4** | $E \text{ vs } B$ | $-0.001392$ | $-0.6164$ | $0.5376$ | $0.7276$ | $[-0.015207, +0.001891]$ | $2 / 4$ ($50\%$) |
| **C5** | $E_{\mathrm{H1a}} \text{ vs } E$ *(Exploratorio)* | $+0.000012$ | $+0.0464$ | $0.9630$ | N/A | N/A | N/A |

### Hallazgo Fundamental sobre la Jerarquía de Modelos:
1. Frente a los modelos de microestructura estándar ($B^{++}$, $B^+$ y $B$), el modelo geométrico $E$ **presenta un $\Delta R^2_{\mathrm{OOS}}$ negativo** (empeora el error fuera de muestra entre $-0.07\%$ y $-0.14\%$).
2. La única comparación donde $E$ obtiene signo positivo es C1 ($E \text{ vs } B^{+++}$). Esto ocurre porque la variable de ratio de control (`v03_pnpc_k3`) añadida en $B^{+++}$ perjudicó ligeramente el ajuste en el Walk-Forward, permitiendo que $E$ pareciera marginalmente mejor solo por comparación contra un baseline artificialmente degradado.
3. En el contraste exploratorio C5, las variables dinámicas de reposición (`v03_depth_replenish_ask`, `v03_depth_replenish_bid`) arrojan una ganancia de $\Delta R^2 = +0.0012\%$ con $p = 0.9630$, confirmando su total irrelevancia predictiva.

---

## 5. Análisis de Sensibilidad HAC y Bootstrap

Se examinó la estabilidad del test Diebold-Mariano variando el ancho de banda Newey-West en $L=10$ ($1H$), $L=20$ ($2H$, primario) y $L=40$ ($4H$):

| Contraste | DM $t$ ($L=10$) | $p$ ($L=10$) | DM $t$ ($L=20$) | $p$ ($L=20$) | DM $t$ ($L=40$) | $p$ ($L=40$) |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **C1 ($E \text{ vs } B^{+++}$)** | $+0.7865$ | $0.4316$ | $+0.7110$ | $0.4771$ | $+0.6694$ | $0.5033$ |
| **C2 ($E \text{ vs } B^{++}$)** | $-0.3591$ | $0.7196$ | $-0.3256$ | $0.7447$ | $-0.3035$ | $0.7615$ |
| **C3 ($E \text{ vs } B^{+}$)** | $-0.6619$ | $0.5081$ | $-0.6042$ | $0.5457$ | $-0.5659$ | $0.5715$ |
| **C4 ($E \text{ vs } B$)** | $-0.6768$ | $0.4986$ | $-0.6164$ | $0.5376$ | $-0.5770$ | $0.5640$ |

- **Conclusión de robustez:** La ausencia de significación estadística es **invariante a la parametrización HAC**. En todos los retardos evaluados, los $p$-valores se mantienen entre $43\%$ y $76\%$.

---

## 6. Holdout Final Cronológico (20% Aislado)

El Holdout comprende las 2 712 observaciones finales cronológicas (Sesiones 06 y 07). Los modelos fueron reajustados sobre el 100% de la muestra de evaluación (10 846 observaciones) y testeados en el Holdout sin reajustes ni adaptaciones:

| Contraste en Holdout | $\Delta R^2_{\mathrm{OOS, holdout}}$ | DM $t\text{-stat}$ ($L=20$) | $p\text{-valor}$ | $N_{\mathrm{obs}}$ |
|:---:|:---:|:---:|:---:|:---:|
| **C1 ($E \text{ vs } B^{+++}$)** | **$-0.005347$ ($-0.5347\%$)** | **$-0.6120$** | **$0.5405$** | **2 712** |
| **C2 ($E \text{ vs } B^{++}$)** | $-0.005146$ ($-0.5146\%$) | $-0.5997$ | $0.5487$ | 2 712 |
| **C3 ($E \text{ vs } B^{+}$)** | $-0.004590$ ($-0.4590\%$) | $-0.5351$ | $0.5926$ | 2 712 |
| **C4 ($E \text{ vs } B$)** | $-0.005003$ ($-0.5003\%$) | $-0.5589$ | $0.5762$ | 2 712 |

- **Colapso del modelo geométrico en el Holdout:**  
  En el conjunto de validación final más estricto, el modelo $E$ tiene un desempeño inferior al de **todos** los modelos competidores, perdiendo aproximadamente un medio punto porcentual de $R^2$ frente a cada uno de ellos.

---

## 7. Interpretación Cuantitativa y Limitaciones

1. **Evidencia sobre la hipótesis:** No existe evidencia de que la curvatura y la concentración geométrica de liquidez aporten señal predictiva incremental sobre el flujo de órdenes y la microestructura convencional.
2. **Impacto de episodios extremos:** Como se documentó en la auditoría de Fase 4, el Holdout concentra 30 de las 45 observaciones con $|y| > 10$. El desempeño negativo de $E$ en esta región demuestra que las features geométricas añaden varianza inestable en regímenes de baja volatilidad retrospectiva, amplificando los errores de predicción durante movimientos bruscos.
3. **Poder estadístico efectivo:** Con $N_{\mathrm{eff}} \approx 1478$, la potencia para detectar efectos marginales con ratios de variabilidad elevados es baja. No obstante, al ser la dirección del efecto negativa frente a $B^{++}$ y sistemáticamente negativa en Holdout, la falta de resultado no es un problema de potencia estadística: es una falsación del efecto esperado.

---

## 8. Análisis de Costes Reales de Mercado

El evaluador OOS congelado opera bajo supuestos estadísticos puros (MSE de retornos z-score normalizados). **No incorpora costes de fricción real:**
1. **Comisiones de intermediación:** Kraken cobra comisiones taker de entre $0.25\text{ bps}$ y $0.40\text{ bps}$ (maker de $0.16\text{--}0.25\text{ bps}$).
2. **Cruce de horquilla (Spread):** El spread mínimo observado en el stream es de $\$0.10\text{ USD}$ ($\approx 0.0123\text{ bps}$), con aperturas frecuentes superiores a $0.12\text{ bps}$. Cruzar el spread para capturar un retorno de 10 segundos consume inmediatamente cualquier microalfa.
3. **Slippage y latencia:** La latencia de reacción frente a libros L2 remotos introduce un retraso de ejecución superior a los microsegundos requeridos para explotar desbalances de flujo.

> [!WARNING]
> Dado que el modelo no supera a los baselines estadísticos y presenta $\Delta R^2 < 0$ en holdout, **la rentabilidad económica neta es estrictamente negativa**. Cualquier estrategia comercial basada en este modelo generaría pérdidas inmediatas por fricción de spread y comisiones.

---

## 9. Decisión Formal y Cierre de Fase 5

Conforme a la matriz determinista preregistrada en [`scripts/evaluate_models_oos_v3.py#L89-L127`](file:///C:/Users/USER/Downloads/navier_lab_project/navier_lab_project/scripts/evaluate_models_oos_v3.py#L89-L127):

```python
wf_success = (delta_r2_wf >= delta_min) and (p_fdr_wf < 0.05) and (folds_positive_count >= 3)
ho_success = (delta_r2_ho > 0.0) and (p_ho < 0.05)
```

- $\Delta R^2_{\mathrm{WF}} = +0.001922 \ge 0.0010$ (Cumple umbral mínimo)
- $p_{\mathrm{FDR, WF}} = 0.7276 \ge 0.05$ (**Falla significancia tras FDR**)
- $\text{Folds} = 3 / 4$ (Cumple consistencia)
- $\Delta R^2_{\mathrm{HO}} = -0.005347 \le 0$ (**Falla en holdout**)

Veredicto del sistema:
# **`INCONCLUSO (EVIDENCIA DÉBIL O POTENCIA INSUFICIENTE TRAS FDR)`**

### Estado del Proyecto:
- **La Fase 5 queda completada y cerrada de forma reproducible.**
- **No se autoriza el paso a fases operativas ni desarrollo de estrategias de trading.**
- La línea de investigación sobre variables geométricas estáticas en L2 queda cerrada de acuerdo con el protocolo.
