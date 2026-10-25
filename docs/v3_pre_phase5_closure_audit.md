# NAVIER V3 — Informe de Auditoría de Cierre Previa a Fase 5

**Auditor:** Auditor Cuantitativo Independiente  
**Fecha:** 2026-10-24  
**Entregable:** `docs/v3_pre_phase5_closure_audit.md`  
**Objetivo:** Cerrar las últimas verificaciones metodológicas de la Fase 4 y dictaminar si el experimento OOS preregistrado está listo para ejecutarse.  
**Script auxiliar utilizado:** `scripts/closure_audit_v3.py` (script único de comprobación de solo lectura).  
**Restricciones:** Cero modificaciones a código congelado, datos, manifiestos o protocolo. Cero modelos entrenados. Cero evaluaciones predictivas ejecutadas.  

---

## 1. Tabla Resumen de Controles de Auditoría

| Control | Descripción de la Verificación | Resultado | Evidencia Concreta | Limitaciones Documentadas |
|---|---|:---:|---|---|
| **C1** | **Verificación Criptográfica Exacta Ruta-Hash** | **`PASS`** | 7 de 7 rutas de [docs/v3_freeze_manifest.md](file:///C:/Users/USER/Downloads/navier_lab_project/navier_lab_project/docs/v3_freeze_manifest.md) coinciden con el SHA-256 calculado byte a byte. | El manifiesto usa tabla Markdown; el emparejamiento ruta-hash fue parseado y verificado unívocamente. |
| **C2** | **Reproducción Temporal de los 7 Clusters ($|y|>10$)** | **`PASS`** | Las 45 observaciones se reproducen y agrupan exactamente en 7 clusters mediante continuidad temporal real en timestamps ($\Delta t \le 10$ s). | No representan 45 eventos independientes: son 7 episodios discretos (duración 1 a 9 segundos). Ninguno cruza fronteras de sesión. |
| **C3** | **Asignación Asimétrica de Clusters a Particiones** | **`PASS`** | Splits 1, 2 y 3 tienen 0 clusters en test; Split 4 tiene 2 clusters (13 obs); Holdout tiene 4 clusters (30 obs). Cluster 1 queda en Train. | El Holdout concentra el 66.7% de los extremos; el Bootstrap de bloques ($1/p=15$ s) tiene $49.8\%$ de probabilidad de cortar episodios de 10 s. |
| **C4** | **Comprobación Empírica de Spreads y Tick Mínimo** | **`PASS`** | En todas las sesiones, el spread en dinero observado colapsa en $\$0.1000$ USD ($98.36\%\text{--}99.85\%$ del tiempo). $\text{Media} > p95$ es matemáticamente consistente por la asimetría extrema ($p99$ alcanza $1.27$ bps). | Se distingue el valor empírico observado ($\$0.10$ USD) de su interpretación institucional de tick en Kraken. |
| **C5** | **Identificación y Arquitectura del Evaluador OOS** | **`PASS`** | El script congelado [scripts/evaluate_models_oos_v3.py](file:///C:/Users/USER/Downloads/navier_lab_project/navier_lab_project/scripts/evaluate_models_oos_v3.py) contiene `evaluate_dataset_v3`. Conserva intactos $C1$, $k=5$, purga (10s), embargo (10s), NW ($L=20$), Bootstrap ($B=1000$) y FDR. | El archivo no cuenta con bloque `if __name__ == '__main__':` CLI; debe ejecutarse mediante llamada a la función autorizada `evaluate_dataset_v3`. |

---

## 2. Detalle de Tareas Ejecutadas y Resultados

### Tarea 1 — Verificación Criptográfica Exacta Pareja Ruta–Hash

Se extrajo cada ruta del archivo congelado [docs/v3_freeze_manifest.md](file:///C:/Users/USER/Downloads/navier_lab_project/navier_lab_project/docs/v3_freeze_manifest.md) y se calculó el hash SHA-256 sobre el archivo real en disco:

| Componente | Ruta del Archivo Congelado | Hash Esperado (Manifiesto) | Hash Calculado (SHA-256) | Coincidencia Exacta |
|---|---|---|---|:---:|
| **Protocolo Científico** | [NAVIER_V3_PROTOCOL.md](file:///C:/Users/USER/Downloads/navier_lab_project/navier_lab_project/NAVIER_V3_PROTOCOL.md) | `0183B474253D5B6F50F25ABA7E463A925A4FF5183DA99A3648736DD93095114A` | `0183B474253D5B6F50F25ABA7E463A925A4FF5183DA99A3648736DD93095114A` | **SÍ** |
| **Pipeline de Features** | [navier_lab/features.py](file:///C:/Users/USER/Downloads/navier_lab_project/navier_lab_project/navier_lab/features.py) | `1B642EBFE827E9348F8DED67F9E5F706D0F6599074156094FB73131A2FA853DB` | `1B642EBFE827E9348F8DED67F9E5F706D0F6599074156094FB73131A2FA853DB` | **SÍ** |
| **Esquema y Config.** | [navier_lab/schema.py](file:///C:/Users/USER/Downloads/navier_lab_project/navier_lab_project/navier_lab/schema.py) | `A34CEC8A9D57B3BDCF8C5B7E803452B33E288B238CBA2F398C66F0FA8CF80E1A` | `A34CEC8A9D57B3BDCF8C5B7E803452B33E288B238CBA2F398C66F0FA8CF80E1A` | **SÍ** |
| **Resampleador Causal** | [navier_lab/resampler.py](file:///C:/Users/USER/Downloads/navier_lab_project/navier_lab_project/navier_lab/resampler.py) | `220BE7754E5377F69D4539B400435F40A6E96257687237E1AC8CF957E3DE7F35` | `220BE7754E5377F69D4539B400435F40A6E96257687237E1AC8CF957E3DE7F35` | **SÍ** |
| **Motor Evaluación OOS** | [scripts/evaluate_models_oos_v3.py](file:///C:/Users/USER/Downloads/navier_lab_project/navier_lab_project/scripts/evaluate_models_oos_v3.py) | `52F566F12BC2728EACEBEEF97EBCCE04133E68D3166BCDEDFD9C6D5F7B67BEDB` | `52F566F12BC2728EACEBEEF97EBCCE04133E68D3166BCDEDFD9C6D5F7B67BEDB` | **SÍ** |
| **Capturador L2 Kraken**| [scripts/capture_kraken_l2.py](file:///C:/Users/USER/Downloads/navier_lab_project/navier_lab_project/scripts/capture_kraken_l2.py) | `D7F01A500F54AC790262AD41806394A8288189E5D31C55F012A57F903C681712` | `D7F01A500F54AC790262AD41806394A8288189E5D31C55F012A57F903C681712` | **SÍ** |
| **Suite de Pruebas V3** | [tests/test_features_v3.py](file:///C:/Users/USER/Downloads/navier_lab_project/navier_lab_project/tests/test_features_v3.py) | `9202EB588BAA451C2CB53E8BE6BA25BB18D08A8195A339EAC6F2818074763118` | `9202EB588BAA451C2CB53E8BE6BA25BB18D08A8195A339EAC6F2818074763118` | **SÍ** |

**Resultado:** `PASS` (7/7 parejas ruta-hash verificadas directamente).

---

### Tarea 2 — Reproducción Temporal de los Siete Clusters con Timestamps

- **Regla exacta de agrupación temporal:**  
  Dos observaciones consecutivas $t_a$ y $t_b$ con $|y| > 10.0$ pertenecen al mismo cluster si y solo si:
  1. `session_id(t_a) == session_id(t_b)` (pertenecen a la misma sesión de captura).
  2. `(timestamp(t_b) - timestamp(t_a)).total_seconds() <= 10.0` (la separación temporal física no excede la ventana prospectiva del target $H=10$ s).

- **Resultados reproducidos:**

| Cluster | Sesión | Filas en Dataset | Timestamps (UTC) | Duración Temporal | Rango de $y$ | Asignación Experimental |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **1** | `v3_val_session_01` | 891 – 892 (2 obs) | `17:15:04` a `17:15:05` | 1 s | $[+10.86, +11.07]$ | **Eval (Train común de splits 1–4)** |
| **2** | `v3_val_session_06` | 10272 – 10274 (3 obs) | `17:46:20` a `17:46:22` | 2 s | $[+10.53, +10.53]$ | **Split 4 Test** |
| **3** | `v3_val_session_06` | 10550 – 10559 (10 obs) | `17:52:06` a `17:52:15` | 9 s | $[-91.49, -43.80]$ | **Split 4 Test** |
| **4** | `v3_val_session_06` | 11161 – 11164 (4 obs) | `18:03:20` a `18:03:23` | 3 s | $[-14.46, -10.66]$ | **Holdout (20% final)** |
| **5** | `v3_val_session_07` | 12010 – 12018 (9 obs) | `18:20:58` a `18:21:06` | 8 s | $[-21.32, -10.38]$ | **Holdout (20% final)** |
| **6** | `v3_val_session_07` | 12941 – 12950 (10 obs) | `18:40:48` a `18:40:57` | 9 s | $[+48.48, +94.89]$ | **Holdout (20% final)** |
| **7** | `v3_val_session_07` | 13198 – 13204 (7 obs) | `18:46:03` a `18:46:09` | 6 s | $[-107.21, -20.19]$ | **Holdout (20% final)** |

- **Comprobación de fronteras:** **Cero clusters cruzan fronteras de sesión** (`Ningun cluster cruza frontera: True`).
- **Comprobación de particiones:**
  * Splits 1, 2 y 3: **0 observaciones extremas en test**.
  * Split 4: **13 observaciones extremas en test** (Clusters 2 y 3).
  * Holdout final: **30 observaciones extremas** (Clusters 4, 5, 6 y 7).

**Resultado:** `PASS` (Los 7 clusters reportados previamente se reproducen de manera idéntica y unívoca).

---

### Tarea 3 — Comprobación Empírica de Spreads y Origen del Tick Mínimo

- **Definición en código congelado:**  
  `spread_bps = (apx - bpx) / mid * 1e4` ([navier_lab/features.py#L78](file:///C:/Users/USER/Downloads/navier_lab_project/navier_lab_project/navier_lab/features.py#L78)).
- **Unidades:** Puntos básicos (**bps**).
- **Spread en dinero observado:** $\Delta P = \mathrm{ask\_px\_1} - \mathrm{bid\_px\_1} = \frac{\texttt{spread\_bps} \times \texttt{mid}}{10^4}$.  
  En el dataset, el valor mínimo absoluto observado es **$\$0.1000$ USD** exactamente.

- **Recálculo por sesión:**

| Sesión | Observaciones | Media (bps) | Mediana (bps) | Percentil 95 (bps) | Máximo (bps) | **% Filas con $\Delta P = \$0.10$ USD** | Obs. $> p95$ | Media de Filas $> p95$ |
|:---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **01** | 2 259 | 0.017383 | 0.012318 | 0.012337 | 1.268667 | **98.36%** | 106 | 0.120269 bps |
| **02** | 1 897 | 0.015638 | 0.012265 | 0.012289 | 0.736878 | **98.79%** | 93 | 0.081164 bps |
| **03** | 1 286 | 0.013336 | 0.012269 | 0.012289 | 0.441469 | **99.53%** | 62 | 0.034446 bps |
| **04** | 2 036 | 0.015313 | 0.012265 | 0.012284 | 1.076700 | **99.21%** | 101 | 0.073782 bps |
| **05** | 2 194 | 0.013028 | 0.012249 | 0.012268 | 0.845953 | **99.68%** | 83 | 0.032807 bps |
| **06** | 2 068 | 0.012644 | 0.012270 | 0.012282 | 0.563949 | **99.85%** | 95 | 0.020413 bps |
| **07** | 1 818 | 0.012449 | 0.012282 | 0.012293 | 0.135132 | **99.78%** | 86 | 0.015864 bps |

- **Distinción metodológica:**  
  *Evidencia observada directa:* El $98.36\%\text{--}99.85\%$ de los libros presentan una diferencia de exactamente $\$0.10$ USD entre mejor ask y mejor bid. A un precio de $\approx \$81\ 300$, esto genera un spread observado de $\approx 0.0123$ bps.  
  *Interpretación del tick:* Este $\$0.10$ USD coincide con la granularidad mínima de cotización observada en el stream. La media supera al $p95$ porque el $5\%$ superior de observaciones tiene una media hasta 10 veces mayor ($0.1203$ bps en S01) por aperturas temporales de horquilla.  
  No se modificó ningún suelo de volatilidad ni se filtró ninguna fila.

**Resultado:** `PASS` (Valores coherentes, evidencia empírica directa distinguida de interpretaciones institucionales).

---

### Tarea 4 — Identificación del Evaluador Correcto y Arquitectura OOS

1. **Resolución de discrepancia de nombres:**
   - [scripts/evaluate_models_oos_v3.py](file:///C:/Users/USER/Downloads/navier_lab_project/navier_lab_project/scripts/evaluate_models_oos_v3.py) es el **archivo congelado** (hash SHA-256: `52F566F1...`).
   - `evaluate_dataset_v3` es la **función Python exportada** dentro de ese archivo ([evaluate_models_oos_v3.py#L253](file:///C:/Users/USER/Downloads/navier_lab_project/navier_lab_project/scripts/evaluate_models_oos_v3.py#L253)).
   - **Hallazgo técnico:** El archivo [scripts/evaluate_models_oos_v3.py](file:///C:/Users/USER/Downloads/navier_lab_project/navier_lab_project/scripts/evaluate_models_oos_v3.py) fue congelado como **módulo de librería sin bloque CLI** `if __name__ == '__main__':` (a diferencia del evaluador de V2).
   - Por tanto, invocar en consola `python scripts/evaluate_models_oos_v3.py --dataset ...` no ejecutaría nada. La ejecución autorizada debe invocar directamente la función `evaluate_dataset_v3(df_features)` desde un runner o wrapper de ejecución.
2. **Confirmación de especificaciones del protocolo en el código congelado:**
   - Contraste primario C1: `("Model_E", "Model_B_tripleplus")` ([L74](file:///C:/Users/USER/Downloads/navier_lab_project/navier_lab_project/scripts/evaluate_models_oos_v3.py#L74)) ✅
   - Folds de Walk-Forward: `k_folds = 5` (4 splits de test) ([L150](file:///C:/Users/USER/Downloads/navier_lab_project/navier_lab_project/scripts/evaluate_models_oos_v3.py#L150)) ✅
   - Purga y Embargo: `purge = 10`, `embargo = 10` ([L150](file:///C:/Users/USER/Downloads/navier_lab_project/navier_lab_project/scripts/evaluate_models_oos_v3.py#L150)) ✅
   - Newey-West: Primario `lags = 20`, sensibilidad `lags = 10` y `lags = 40` ([L306-L308](file:///C:/Users/USER/Downloads/navier_lab_project/navier_lab_project/scripts/evaluate_models_oos_v3.py#L306-L308)) ✅
   - Bootstrap: `stationary_block_bootstrap_ci` ($B = 1000$, $p_{\mathrm{geo}} = 1/15$, semilla 42) ([L221-L225](file:///C:/Users/USER/Downloads/navier_lab_project/navier_lab_project/scripts/evaluate_models_oos_v3.py#L221-L225)) ✅
   - Comparaciones múltiples: `bh_adjust` (Benjamini-Hochberg FDR 5% sobre C1..C4) ([L349-L351](file:///C:/Users/USER/Downloads/navier_lab_project/navier_lab_project/scripts/evaluate_models_oos_v3.py#L349-L351)) ✅
   - Holdout: `holdout_ratio = 0.20` (último 20% cronológico preservado intacto) ([L253](file:///C:/Users/USER/Downloads/navier_lab_project/navier_lab_project/scripts/evaluate_models_oos_v3.py#L253)) ✅

**Resultado:** `PASS` (Protocolo y motor 100% verificados e intactos).

---

## 3. Decisión Final de la Auditoría

# **`READY FOR AUTHORIZATION`**

### Dictamen del Auditor Cuantitativo:
Todas las comprobaciones críticas requeridas por la auditoría han sido verificadas empírica y criptográficamente de manera directa:
1. Las 7 parejas ruta-hash congeladas coinciden exactamente byte a byte con el manifiesto original.
2. Los 7 clusters de colas pesadas ($|y| > 10$) quedan delimitados en tiempo real (1 a 9 s), respetan estrictamente las fronteras de sesión y demuestran que los Splits 1, 2 y 3 del walk-forward están 100% limpios de extremos.
3. La paradoja de los spreads ($\text{Media} > p95$) queda resuelta analíticamente por la masiva acumulación en el tick de $\$0.10$ USD ($>98.3\%$) y la asimetría positiva de la cola derecha.
4. La divergencia entre `evaluate_models_oos_v3.py` y `evaluate_dataset_v3` queda resuelta sin alterar archivos congelados.

**Aviso de restricción:**  
Este dictamen **no constituye autorización de ejecución**. La Fase 5 permanece formalmente bloqueada a la espera de la orden explícita del investigador principal.
