# NAVIER V3 — borrador de diseño confirmatorio

**Estado:** borrador para revisión; no preregistrado ni autorizado para ejecutar.  
**Base:** `NAVIER_V3_PROTOCOL.md` (hash revisado `0183b474253d5b6f50f25aba7e463a925a4ff5183da99a3648736dd93095114a`).  
**Separación de evidencia:** los resultados históricos son post hoc y no se reutilizan como confirmación.

## 1. Hipótesis falsable

La hipótesis primaria H1 del protocolo dice que un mismo OFI/imbalance produce respuestas de precio distintas según la vulnerabilidad geométrica local de la liquidez contraria. Operacionalmente, el Modelo E debe mejorar la predicción del retorno normalizado a 10 s frente a B+++, que ya incluye el flujo, imbalance, profundidad, retardos, interacciones convencionales y `v03_pnpc_k3`.

El contraste principal es **C1: E vs B+++**. Las variables H1a de reposición permanecen exploratorias y no pueden sustituir H1 después de observar el bloque independiente.

## 2. Target, horizonte y muestra

El target primario congelado es:

`r10_norm(t) = [ln(mid(t+10) / mid(t)) × 10^4] / [σ̂₆₀,bps(t) × √10]`.

El horizonte primario es 10 s. Los horizontes 5 s y 30 s son de robustez, no confirmatorios. El protocolo excluye `σ̂₆₀(t) < 0.01 bps`, discontinuidad en `(t, t+10]` y staleness futura superior a 1.000 ms. El criterio del bloque también exige al menos 6.500 observaciones limpias, con `gap_future` ausente y `σ̂₆₀ ≥ 0.01 bps`.

La regla de muestra común requiere que B, B+, B++, B+++ y E se ajusten y evalúen sobre las mismas filas en que todas las variables de E y el target son válidos. La cobertura y exclusiones deben contarse antes de ajustar; no se deben quitar sesiones por su resultado.

## 3. Baseline y comparación justa

El baseline decisivo es **B+++**, y el Modelo E añade la geometría V3 preespecificada. B+++ incluye B, retardos de B+, interacciones B++, y `v03_pnpc_k3`. La comparación E–B+++ aísla si las otras variables geométricas de E añaden información una vez controlada la razón presión/profundidad.

Para impedir ventajas artificiales:

- Usar la misma muestra común, target, folds, orden temporal y observaciones OOS para ambos modelos.
- Aplicar la normalización usando solo el train de cada fold.
- Mantener OLS/ridge con `λ = 1e-6 × N_train`; no volver a seleccionar features ni hiperparámetros usando validación u holdout.
- Reportar también baselines B, B+ y B++ solo conforme a la jerarquía preespecificada una vez resueltas las contradicciones del protocolo indicadas abajo.
- Reservar E_H1a para análisis exploratorio en su submuestra limpia.

## 4. Métrica e incertidumbre

La métrica primaria es `ΔR²_OOS = 1 − MSE_E / MSE_B+++`, agregada sobre la unión de los cuatro bloques de test walk-forward. El umbral de relevancia mínima práctica descrito para C1 es `δ_min = 0.0010`.

La inferencia escrita en §8.4 del protocolo prescribe Diebold–Mariano sobre diferencias pareadas de error cuadrático, varianza HAC Newey–West, ancho primario `L=20` y sensibilidades `L=10` y `L=40`. También prescribe BH al 5% para la familia confirmatoria y bootstrap estacionario de Politis–Romano con longitud media 15 s, 1.000 réplicas, semilla 42 e intervalo al 95%. Deben conservarse los cuatro deltas por fold y exigir la consistencia definida en la regla de decisión.

**Decisión pendiente:** §8.4 llama confirmatorios a C1–C4 para BH; Fase 5 ordena DM/FDR solo para C1–C3 y llama C4 exploratorio. La evaluación histórica usa bootstrap temporal por bloques como método inferencial principal, no el DM-HAC descrito en §8.4. Hace falta aprobación de una única jerarquía, familia FDR e inferencia primaria antes de congelar el análisis; no se debe escoger la variante después de ver resultados.

## 5. Validación temporal y tamaño de muestra

El diseño de captura especifica al menos 9 sesiones de aproximadamente 40 minutos en franjas variadas, incluidas al menos dos en horario europeo y dos americano; mínimo 6.500 observaciones limpias. Holdout final: último 20%, intocable durante el desarrollo; walk-forward expansivo con `k=5`, cuatro test splits, purge de 10 observaciones, embargo de 10 observaciones y escalado en train.

El protocolo tiene una entrada de desviación que registra una captura previa reducida de 9 a 7 sesiones y 15.762 observaciones limpias. Esa nota documenta una desviación histórica; no demuestra por sí sola que un nuevo bloque prospectivo pueda reducir el mínimo de sesiones. La muestra confirmatoria nueva debe seguir los criterios vigentes salvo que se apruebe y registre una enmienda antes de capturar.

## 6. Dependencia temporal, selección y costes

- Los retornos primarios de 10 s se solapan en las observaciones de 1 s; el protocolo reconoce dependencia MA(9) y fija HAC L=20, con análisis L=10/40. Se respetan los límites de sesión/fold/gaps durante remuestreos y purga/embargo según la implementación aprobada.
- Las features, sus fórmulas, la familia E, el target y la jerarquía de modelos deben quedar congelados antes de abrir el bloque. No seleccionar features por correlaciones, p-valores o residuos del holdout. Reportar descriptivos/colinealidad solo en la fase y bajo las reglas escritas.
- La significación predictiva no implica utilidad económica. La Fase 7 solo procede tras aceptar H1 y requiere spread observado, comisiones aplicables, slippage por tamaño de posición y latencia de al menos 50 ms. El protocolo no define tamaño de posición, modelo de ejecución, regla de señal ni umbral neto de aceptación; esos elementos requieren un plan económico separado y aprobación previa. No afirmar rentabilidad antes de ese análisis.

## 7. Regla de interpretación de C1

Aplicar literalmente la clasificación MECE de §8.3 tras resolver la familia estadística. El éxito requiere `ΔR²_WF ≥ 0.0010`, p ajustado C1 < 0.05, al menos 3/4 folds con delta positivo y holdout con `ΔR² > 0` y p < 0.05. Según la regla vigente, delta WF no positivo o menos de 2/4 folds positivos se clasifica como fracaso; delta positivo pero menor que 0.0010 con al menos 2/4 folds se clasifica como futilidad. Estos resultados permitirían concluir falta de valor incremental bajo las condiciones examinadas; no demostrarían que ninguna señal NAVIER pueda funcionar en cualquier régimen. Los casos restantes que no alcanzan éxito deben conservarse como inconclusos o discrepancia de holdout según las reglas congeladas.

## 8. Históricos: solo diagnóstico

`results/phase5_v3_purged_run4/oos_evaluation_results.json` está etiquetado `POST_HOC_DIAGNOSTIC_NOT_CONFIRMATORY`. Registra 13.558 observaciones limpias, 8.637 observaciones OOS walk-forward, C1 (`Model_E` vs `Model_B_tripleplus`) con `ΔR²_WF = 0.0019218`, 3/4 folds positivos, p ajustado reportado 0.6633 y `ΔR²_holdout = −0.0053281` con p reportado 0.4226; su veredicto es INCONCLUSO. El artefacto usa bootstrap por bloques. Ninguna cifra se interpreta como evidencia confirmatoria ni se actualiza con este documento.

## 9. Aprobaciones necesarias antes de congelar

1. Resolver C2–C4 y la discordancia entre §8.1/§8.4 y Fase 5: lista confirmatoria, FDR y papel de C4.
2. Fijar el estimador inferencial primario: DM-HAC como en §8.4 o bootstrap como en el evaluador histórico; decidir si el segundo queda como sensibilidad y cómo se reportan los IC.
3. Confirmar que un bloque prospectivo nuevo cumplirá ≥9 sesiones y horarios, además de ≥6.500 observaciones limpias; documentar el tratamiento de las siete sesiones previas.
4. Revisar la implementación efectiva de evaluación contra el protocolo antes de abrir el bloque, incluida la disponibilidad de Modelo B+++ y la consistencia del holdout.
5. Antes de cualquier Fase 7, aprobar por separado tamaño de posición, reglas de entrada/salida, comisiones, slippage, latencia y criterio económico neto.

Este borrador no cambia el protocolo, no desbloquea datos, no ejecuta evaluación y no sustituye una preregistración aprobada.
