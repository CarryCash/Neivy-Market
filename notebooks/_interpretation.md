## 8. Veredicto: qué está validado y qué NO

### Lo que muestran los resultados (sintéticos)

| Mundo | Verdad plantada | Resultado del pipeline | ¿Correcto? |
|---|---|---|---|
| **S0 ruido** | nada | 0 de 24 variables significativas (FDR 5 %); ΔR² OOS ≈ 0; veredicto **sin señal** | ✅ |
| **S1 tradicional** | solo flujo $f$ | 8 variables significativas (imbalance, volúmenes, rezagos…) y **1 Navier** (`dI_dt`, por correlación con $f$); aporte incremental Navier nulo (ΔR² ≈ −0.02 %); veredicto **sin señal** | ✅ |
| **S2 Navier** | $f$ + gradiente + aceleración | 7 variables Navier significativas; ΔR² OOS = +0.44 % sobre B+ (R² 4.0 % → 4.4 %), 5/5 folds, DM p < 0.001, Wald p ≈ 0, placebo p ≈ 0.007; veredicto **señal** | ✅ |
| **Monte Carlo** (20 semillas × {S0, S1}) | sin señal Navier | **0 / 40** veredictos "señal"; el p del Wald bajo 5 % en 5 % de corridas (uniforme, como debe) | ✅ |

Hallazgos que importan para los siguientes pasos:

1. **Sin el control B+ habríamos sido engañados.** En S1, `dI_dt` sale univariadamente significativa aunque no tiene información propia (es una diferencia de imbalance). El análisis univariado **no** basta; la conclusión salió del test incremental.
2. **La inferencia ingenua es inservible aquí:** rechaza la nula en 28–52 % de los casos (nominal 5 %). El t-HAC queda en 4–8 % (ligeramente liberal): por eso se exige acuerdo entre HAC, permutación, FDR, OOS, DM y placebo.
3. **Potencia:** con ~28 h de datos, el pipeline detecta la señal plantada al 100 %; al 75 % y 50 % el Wald (dentro de muestra) ya la ve pero el criterio completo (OOS + DM) **no** → un efecto Navier 2–4× más débil que el plantado **se nos escaparía**. "No detectamos señal" nunca significará "no hay señal".
4. **Sensibilidad al horizonte:** a H = 30 s la señal plantada deja de pasar los 4 criterios (DM p ≈ 0.03 > 1 %). En S1 a H = 30 el bloque Navier *empeora* significativamente fuera de muestra (sobreajuste, ΔR² = −0.39 %); el criterio 2 exige ΔR² > 0 y lo rechaza correctamente.
5. **Colinealidad:** VIF máximo ≈ 46 en el modelo completo (imbalance con sus rezagos). No sesga las predicciones OOS pero sí vuelve inestables los coeficientes individuales → no interpretar coeficientes aislados.

### ✅ Validado
- Recolector/preprocesador **sin look-ahead** y con streaming **idéntico** al cálculo en bloque (5 pruebas automáticas).
- Memoria acotada (chunks de 20 000 filas; solo se cargan las variables, ~16 MB por mundo, no el L2 crudo).
- Contrato de datos L2 (10 niveles, 1 s) con validador de integridad.
- La metodología estadística (HAC + permutación circular + FDR + walk-forward con purga + DM + Wald + placebo) **no inventa señal** en mundos sin ella (0/40) y **la encuentra** cuando existe y es lo bastante fuerte.
- Criterios de decisión pre-registrados y aplicados de forma mecánica.

### ❌ NO validado (todavía)
- **Nada sobre el mercado real.** Ninguna conclusión de este notebook dice si BTC/USDT contiene esta señal.
- Que las variables Navier (definiciones operacionales) tengan **algún** sentido económico/físico en un libro real.
- La **magnitud** de la señal plantada (c_τ, c_acc) se fijó *después* de un barrido de potencia para que fuera detectable: sirve para probar el detector, no como estimación de nada. Los R² del 4 % son irrealistas para datos reales (esperaríamos ≪ 1 %).
- **OFI** calculado sobre snapshots de 1 s (no eventos): aproximación. Con datos reales conviene el OFI a nivel evento.
- El sintético no incluye: cambios de régimen, saltos, huecos de conexión, latencia, ni la dinámica de reposición de liquidez → el pipeline **no** ha sido puesto a prueba contra estos.
- `to_1s_grid` (evento → 1 s) probado solo en un caso sintético y **sin acarreo del segundo incompleto entre chunks**.
- El **placebo** por desplazamiento circular es una nula algo pesimista (rompe también la colinealidad del bloque Navier con el baseline; por eso en S0/S1 da p ≈ 0.03–0.05 aunque no haya señal). Por sí solo el criterio 4 es débil; el veredicto descansa en los 4 juntos (0/40 falsos positivos).
- Costos, slippage, latencia, economía de la estrategia: fuera de alcance de V0.1.

### 🛑 Punto de parada — decisiones para hacer JUNTOS antes de datos reales
1. **Fuente y captura:** WebSocket L2 (`book`, depth 10) de Kraken; ¿cuántas horas/días? (Sugerencia: 24–72 h continuas, en un solo régimen y luego otro, para evaluar estabilidad.)
2. **Reducción:** guardar solo 10 niveles y estado a rejilla de 1 s (≈ 100 000 filas/día ≈ 20 MB en Parquet) en vez de todos los eventos; ¿conservar además una muestra de eventos para calcular OFI exacto?
3. **Datos faltantes y reconexiones:** política ante huecos (descartar ventana vs. ffill).
4. **Partición pre-registrada:** reservar un tramo final **sin tocar** como conjunto de prueba único.
5. **Umbral mínimo de efecto relevante** (en bps, neto de costos) que justificaría pasar al Notebook 002, dada la potencia calculada arriba.
6. **Qué haremos si el veredicto es negativo:** modificar definiciones *antes* de mirar el conjunto de prueba, o descartar la hipótesis.

> *Si la hipótesis no funciona, el modelo debe demostrarlo, no intentar hacer que funcione.*
