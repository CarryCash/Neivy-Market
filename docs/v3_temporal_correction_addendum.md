# NAVIER V3 — Addendum post hoc de integridad temporal

**Estado:** corrección diagnóstica posterior a la apertura de los datos V3.  
**Fecha:** 2026-10-24.  
**Protocolo V3 original:** permanece sin cambios en `NAVIER_V3_PROTOCOL.md`.  
**Evidencia producida con este addendum:** diagnóstico post hoc; no es una prueba confirmatoria independiente.

## Motivo

La evaluación V3 archivada partió las filas comunes 80/20, y ajustó el modelo de holdout con todas las etiquetas del 80% inicial. El objetivo original se genera por `shift(-H)` sobre una rejilla de un segundo; por ello, una fila de entrenamiento cercana al corte usa precios del período que el protocolo llamaba holdout. La revisión encontró un último origen train a las 17:57:41 UTC con etiqueta que terminaba a las 17:57:51 UTC, mientras que el holdout empezaba a las 17:57:42 UTC.

## Metadata de tiempo

El constructor derivará los campos en cada sesión, antes de descartar filas:

- `feature_time`: timestamp del estado L2 resampleado que sirve como origen de las features. En estos artefactos es el timestamp de mercado del bin; no representa tiempo de recepción del cliente ni latencia de decisión.
- `label_start_time`: `feature_time`, porque el retorno es `log(mid(t+H)/mid(t))`.
- `label_end_time`: timestamp del estado futuro que realmente usa `shift(-H)` en el grid de 1 s.
- `label_end_session_id`: sesión del estado futuro; debe coincidir con la sesión de origen.
- `label_horizon_seconds`: horizonte usado al construir el target.

El constructor exige un grid de exactamente un segundo. El evaluador rechaza metadata ausente, endpoints/horizontes inconsistentes, timestamps sin zona horaria o sesiones cruzadas. No reconstruye el endpoint a partir del número de filas del dataset filtrado.

## Partición y reglas

- **Purga:** se admite una observación train solo si `label_end_time < nominal_test_start_time`. El filtro utiliza el final temporal real de la etiqueta; no usa un número de filas como sustituto del horizonte.
- **Embargo:** descarta observaciones del inicio del test durante `embargo_seconds` de tiempo transcurrido. No sustituye a la purga.
- El holdout mantiene el corte cronológico del 20% de observaciones para comparabilidad, pero ninguna etiqueta train puede alcanzar el timestamp de inicio nominal del holdout. El embargo de 10 segundos se mide por timestamps.
- Cada target permanece unido a su fila original. Features y targets se generan independientemente por sesión; etiquetas que cruzan sesiones se rechazan.
- Una rejilla desordenada se ordena de forma estable por `feature_time`; índices duplicados, tiempos ausentes, tiempos duplicados y folds vacíos/pequeños generan errores explícitos.

## Inferencia

La salida corregida utiliza diferencias pareadas de error cuadrático y un moving block bootstrap en tiempo transcurrido con longitudes de 10, 15 y 30 segundos. La longitud primaria es 15 segundos: 1.5 veces el horizonte predefinido de 10 segundos, coherente con la dependencia inducida por targets solapados; 10 y 30 segundos son sensibilidad a 1H y 3H. Los bloques no cruzan sesión, fold de test ni gaps superiores a la longitud examinada. El p-valor se obtiene de la distribución bootstrap centrada bajo media de diferencia de pérdidas cero. Benjamini–Hochberg se mantiene sobre C1–C4 con los p-valores primarios de 15 segundos; C5 sigue exploratorio.

Este procedimiento mejora el respeto de dependencia serial dentro de segmentos observados, pero no crea sesiones independientes ni revierte el hecho de que los resultados V3 ya se inspeccionaron. Los nuevos resultados históricos se etiquetan `POST_HOC_DIAGNOSTIC_NOT_CONFIRMATORY`.

## Ejecución y conservación

El nuevo dataset se escribe en `data/research_dataset_v3_temporal_purged.parquet` con manifiesto separado. El runner escribe únicamente en `results/phase5_v3_purged/` y aborta si ese directorio contiene archivos. No se sobrescriben `data/research_dataset_v3.parquet`, `results/phase5_v3/` ni `docs/v3_freeze_manifest.md`.
