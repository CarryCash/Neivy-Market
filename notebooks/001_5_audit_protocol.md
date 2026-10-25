# NAVIER 001.5 — Protocolo de auditoría

## Alcance
Auditoría técnica de V0.1 sintética; no prueba hipótesis de mercado ni rentabilidad.

## Reglas
1. Mantener intactos los artefactos de Notebook 001.
2. Registrar toda modificación como versión nueva.
3. No conectarse a Kraken durante esta etapa.
4. No elegir thresholds después de observar el resultado sin declararlo.
5. Separar hallazgo, evidencia, severidad, corrección propuesta y test de regresión.

## Orden de trabajo
1. Reproducibilidad del entorno.
2. Contrato e integridad de snapshots L2.
3. Fórmulas y estabilidad numérica.
4. Causalidad de features y definición del target.
5. Folds temporales, purga y evaluación fuera de muestra.
6. Pruebas unitarias adicionales.
7. Criterios explícitos para autorizar la captura real.
