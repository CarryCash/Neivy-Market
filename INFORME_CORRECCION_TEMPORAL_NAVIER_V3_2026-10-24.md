# NAVIER — corrección mínima del evaluador V3 y validación temporal

**Fecha:** 24 de octubre de 2026  
**Conclusión:** se corrigió y ejecutó la evaluación V3 con purga del horizonte de etiqueta y embargo explícito. El solapamiento quedó eliminado en los splits auditados, sin sobrescribir los artefactos previos. La corrida es diagnóstica post hoc, no confirmatoria: el holdout V3 ya había sido consultado antes de corregirlo. No hay evidencia de rentabilidad neta.

## A. Estado actual

- Proyecto restaurado desde el ZIP existente; no se reconstruyó desde cero.
- El protocolo congelado NAVIER_V3_PROTOCOL.md no cambió (SHA-256 0183b474253d5b6f50f25aba7e463a925a4ff5183da99a3648736dd93095114a).
- Se preservó el evaluador histórico como legado; el punto de entrada público deriva al evaluador temporal nuevo.
- El dataset original conserva SHA-256 5e7139209e8ee62bfbd6a04f6387e8ba987894f98da75372b2a5a15645c0f7d8. El resultado histórico conserva SHA-256 9cb3f7bf7bd8446a771e9c2410996d445759ce0646c88f09dd0535d81428fd95.
- No se ejecutaron órdenes, ni se conectó el sistema a trading.

## B. Flujo de datos

Capturas L2 históricas por sesión → builder V3 con grilla de 1 s → variables de microestructura y geométricas + retorno futuro a 10 s → metadatos de inicio/fin de etiqueta → dataset temporal de 13 558 filas en 7 sesiones → walk-forward de 4 folds y holdout de 20%, con purga y embargo → comparación Model_E contra cuatro baselines → bootstrap temporal pareado (10/15/30 s), BH en C1–C4 → resultados JSON y metadata.

Las marcas disponibles son marcas del conjunto como proxy de tiempo de mercado. No hay timestamp de recepción que permita estimar latencia efectiva.

## C. Estado de componentes

| Componente | Estado | Evidencia / límite |
|---|---|---|
| Protocolo V3 | Verificado | Hash coincide con el congelado. |
| Datos/resultados originales | Verificado | Hashes antes/después idénticos. |
| Builder temporal | Verificado | 13 558 filas, 7 sesiones; rejilla 1 s. |
| Etiqueta futura | Verificado | Inicio coincide con feature time; fin efectivo del shift(-H), horizonte exacto 10 s y misma sesión. |
| Purga/embargo walk-forward | Verificado | 4/4 folds sin solapamiento; purga por endpoint y embargo 10 s. |
| Purga/embargo holdout | Verificado | Último fin de etiqueta train 17:57:41 UTC, inicio nominal test 17:57:42; test efectivo inicia 17:57:59 tras embargo. |
| Inferencia | Verificado en ejecución | Bootstrap por bloques de tiempo dentro de sesión/fold, sensibilidad 10/15/30 s; BH para cuatro comparaciones. Holdout ya observado. |
| Comparación predictiva | Verificado | Cuatro contrastes walk-forward y cuatro holdout ejecutados. |
| Evaluación de trading neta | Incompleto | No hay fills, comisión, slippage, latencia ni PnL neto. |
| Test confirmatorio | Fallido para uso confirmatorio | El holdout ya fue consultado; corrida corregida sólo diagnóstica. |

## D. Pruebas y resultados observados

- Suite completa: 59 passed, 1 warning en 6.19 s. Warning esperado de división por cero en prueba de precio constante (Re_m infinito).
- Pruebas temporales nuevas: 11 passed; incluyen frontera de etiqueta, timestamps irregulares, sesiones, índices duplicados, metadatos ausentes, folds vacíos/pequeños, determinismo e integración sin solapamiento.
- Construcción del dataset: exitosa; warning numérico esperado en estrés de precio constante.
- Runner final: SUCCESS, 1 000 réplicas, semilla 42, hashes fuente coincidentes.
- Tres intentos previos fallidos quedaron preservados en phase5_v3_purged, run2 y run3: fallos de preflight, validación de columnas derivadas y salida de consola CP1252 tras guardar resultado. No son corridas válidas. La corrida final es run4.
- No se reescribieron los outputs históricos.

## E. Evidencia predictiva

Métrica: delta de R² OOS (Model_E menos baseline). Bootstrap pareado de pérdida cuadrática; p primario a 15 s y BH C1–C4. Muestra walk-forward 8 637; holdout 2 705.

| Walk-forward | ΔR² | IC 95% | p 15 s | p BH | Folds + |
|---|---:|---:|---:|---:|---:|
| E vs B_tripleplus | +0.001922 | [-0.007412, +0.005244] | 0.456 | 0.663 | 3/4 |
| E vs B_plusplus | -0.000736 | [-0.013185, +0.002471] | 0.719 | 0.719 | 2/4 |
| E vs B_plus | -0.001325 | [-0.015046, +0.002037] | 0.495 | 0.663 | 2/4 |
| E vs B | -0.001392 | [-0.015698, +0.002008] | 0.498 | 0.663 | 2/4 |

En holdout E vs B_tripleplus: ΔR²=-0.005328, IC 95% [-0.037368, +0.006136], p=0.423. Los otros tres contrastes de holdout también tienen delta negativo e intervalos que contienen cero. C5 exploratorio: ΔR²≈+0.000012, p≈0.962.

El pequeño estimado positivo del primer contraste walk-forward es incierto, inconsistente entre folds, no supera FDR y se invierte en holdout. Esto no demuestra que no exista ninguna señal posible; estos datos no demuestran valor incremental. No se infiere rentabilidad de R².

## F. Brechas que impiden concluir valor

1. Holdout ya inspeccionado: falta periodo futuro intacto con protocolo congelado antes de abrirlo.
2. Siete sesiones y un horizonte de 10 s: representatividad y potencia limitadas.
3. Sin simulación de ejecución ni costes: fees, spread, slippage, latencia, selección adversa e inventario.
4. Sin timestamp de recepción para probar disponibilidad de features al tomar decisión.
5. El bootstrap atiende dependencia temporal, pero no revierte selección previa ni consultas al holdout.
6. No hay análisis suficiente de estabilidad por régimen ni distribución de PnL/riesgo de cola.

## G. Experimento mínimo siguiente

**Hipótesis:** las variables geométricas V3 mejoran la pérdida OOS frente al baseline más fuerte predefinido en sesiones futuras intactas y el efecto sobrevive a costes conservadores.

Congelar/hash de variables, target 10 s, modelo, comparador y métrica antes de recolectar/abrir nuevas sesiones; capturar timestamp de exchange y recepción; hacer una sola evaluación prospectiva y bootstrap temporal. Sólo si supera ese filtro, simular ejecución con comisiones configuradas, spread y slippage/latencia observados, sin órdenes reales.

**Aceptación:** separación causal íntegra; protocolo preregistrado; datos posteriores al freeze; mejora práctica predefinida con intervalo de incertidumbre favorable y sin depender de un solo fold; PnL neto positivo y riesgo cuantificado tras costes.

**Estimación:** 1–2 días de ingeniería para captura temporal y runner prospectivo; 1–3 días para simulador de costes una vez definidos los fees y disponibles datos de recepción. Calendario de adquisición depende de potencia y estabilidad; no puede fijarse con siete sesiones.

## H. Archivos candidatos para la siguiente etapa; no modificados

- navier_lab/collector.py o módulo efectivo de captura: timestamps de exchange y recepción.
- navier_lab/schema.py: campos temporales y calidad de sincronización.
- scripts/build_research_dataset_v3.py: extensión causal para capturas nuevas.
- scripts/evaluate_models_oos_v3_temporal.py: evaluación prospectiva preregistrada si se requiere.
- Módulo acotado de simulación de costes, después de definir supuestos observables.
- Pruebas correspondientes en tests/.

No se modifican ahora.

## I. Artefactos y reproducibilidad

- Resultado: results/phase5_v3_purged_run4/oos_evaluation_results.json — SHA-256 54693a7257d12b3426850678bc7189c0608b953902f3caba3e0561ff0f078c0d.
- Metadata: results/phase5_v3_purged_run4/execution_metadata.json — SHA-256 255dff9f9ff273d01e03e86ff19aa2490ed0db025881fca1ad32b01e78c29aa3.
- Dataset temporal: data/research_dataset_v3_temporal_purged.parquet — SHA-256 4a337ef506b3a5a18d50a3d3e45626658a4c7f2a469c9435dac618450c6948be; manifest compañero en data/research_dataset_v3_temporal_purged.manifest.json.
- Código temporal: scripts/evaluate_models_oos_v3_temporal.py, scripts/run_phase5_evaluation_purged.py, scripts/build_research_dataset_v3.py; pruebas: tests/test_evaluate_models_oos_v3.py.
- Addendum y manifest de freeze: docs/v3_temporal_correction_addendum.md y docs/v3_temporal_correction_manifest.json.
- El workspace no tenía commits; el contenido restaurado aparece como no rastreado y no existe una base Git versionada para afirmar un diff histórico fiable.

