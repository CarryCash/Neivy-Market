"""navier_lab — Proyecto NAVIER V0.1: ¿contienen señal las variables inspiradas en fluidos?

Módulos
-------
schema     : contrato de datos L2 (columnas canónicas) y configuración
synthetic  : generador de L2 sintético con "verdad conocida" (3 mundos)
collector  : fuentes de datos intercambiables (sintética, parquet, stub Kraken)
features   : cálculo de variables (causal, ventana finita) + streaming por chunks
analysis   : estadística (HAC, permutación circular, walk-forward, DM, placebo)
"""
