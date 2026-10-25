# NAVIER V3 — Manifiesto de Captura Independiente (Fase 3)

**Estado:** CERRADO — 7 sesiones completadas  
**Generado:** 2026-10-23  
**Símbolo:** BTC/USD · Kraken Spot WebSocket v2 · Profundidad 10 niveles  

> [!IMPORTANT]
> Los datos de `data/v3_validation/` son INVIOLABLES para modelado hasta completar la evaluación (Fase 5). No abrir, explorar ni usar para elegir features, ajustar parámetros o cambiar umbrales.

---

## Resumen ejecutivo

| Métrica | Valor | Requisito protocolo |
|---------|------:|:---:|
| Sesiones completadas | 7 | ~~9~~ (desviación documentada §12) |
| Observaciones raw totales | 1 054 779 | — |
| Bins 1s totales | 16 750 | — |
| **Observaciones limpias (1s, sin gaps)** | **15 762** | ≥ 6 500 ✅ |
| Checksum failures acumulados | 0 | 0 |
| Sesiones con `VALID` final | 7/7 | 7/7 ✅ |

---

## Tabla de sesiones

| Sesión | Inicio (UTC) | Fin (UTC) | Filas raw | Reconex. | Bins 1s | Gaps | **Clean** | SHA-256 (parquet raw) |
|--------|-------------|----------|----------:|:---:|--------:|-----:|----------:|----------------------|
| 01 | 2026-10-22 16:58:50 | 2026-10-22 17:56:25 | 183 933 | 0 | 2 369 | 0 | **2 369** | `c3e71b83...` |
| 02 | 2026-10-23 14:46:05 | 2026-10-23 15:26:11 | 213 143 | 5 | 2 396 | 187 | **2 209** | `2e573a9c...` |
| 03 | 2026-10-23 15:26:27 | 2026-10-23 16:06:32 | 114 582 | 16 | 2 391 | 759 | **1 632** | `bbfe23e9...` |
| 04 | 2026-10-23 16:09:16 | 2026-10-23 16:49:21 | 177 229 | 2 | 2 399 | 42 | **2 357** | `59e6cad3...` |
| 05 | 2026-10-23 16:54:05 | 2026-10-23 17:34:05 | 151 276 | 0 | 2 398 | 0 | **2 398** | `87318ade...` |
| 06 | 2026-10-23 17:34:23 | 2026-10-23 18:14:28 | 124 065 | 0 | 2 399 | 0 | **2 399** | `b1cbabb9...` |
| 07 | 2026-10-23 18:14:45 | 2026-10-23 18:54:45 | 90 551 | 0 | 2 398 | 0 | **2 398** | `b9276e35...` |
| **Total** | | | **1 054 779** | **23** | **16 750** | **988** | **15 762** | |

> [!NOTE]
> Sesión 03: 16 reconexiones por inestabilidad de red momentánea. `checksum_failures = 0` en todas las reconexiones — el libro se revalidó con snapshot completo cada vez. El mayor número de gaps (759 bins) refleja los periodos de reconexión; el resto de la sesión es íntegra.

---

## Hashes SHA-256 — archivos de datos (raw L2)

```
v3_val_session_01_btc_usd_l2.parquet  c3e71b83b9e3ada992e9c32756c6b094ae48c99c7ab681e871d832b2d27261d5
v3_val_session_02_btc_usd_l2.parquet  2e573a9c3a66cf5dd1a080babe0850a62db1e0fa8a30b427b883977d0ddff1af
v3_val_session_03_btc_usd_l2.parquet  bbfe23e9f53aa23b9bd5129e0d0eb4ce4473b4bef91509e8285c0436f1f842de
v3_val_session_04_btc_usd_l2.parquet  59e6cad3cf96bbc96b2d12f11207fd2c7d326a69c24831b5d995c724d44998a3
v3_val_session_05_btc_usd_l2.parquet  87318ade0521a6d0b52a3273027dddefadffb9a6ab311f9b2120e08b2e382da6
v3_val_session_06_btc_usd_l2.parquet  b1cbabb9af9fd5c8a14d0252cf7a40fc58e0ffa52231eb5a909e7821e277118d
v3_val_session_07_btc_usd_l2.parquet  b9276e35c20ae2bce67cc24fe741815f667ff3931240961e2ccd53c13502fc24
```

---

## Hashes SHA-256 — código congelado (post-captura)

```
NAVIER_V3_PROTOCOL.md              0183B474253D5B6F50F25ABA7E463A925A4FF5183DA99A3648736DD93095114A
scripts/evaluate_models_oos_v3.py  52F566F12BC2728EACEBEEF97EBCCE04133E68D3166BCDEDFD9C6D5F7B67BEDB
scripts/capture_kraken_l2.py       D7F01A500F54AC790262AD41806394A8288189E5D31C55F012A57F903C681712
tests/test_features_v3.py          9202EB588BAA451C2CB53E8BE6BA25BB18D08A8195A339EAC6F2818074763118
```

> [!CAUTION]
> `capture_kraken_l2.py` fue modificado durante la captura (adición de `--progress-interval` para heartbeat). Esta modificación es exclusivamente operativa — no afecta la lógica de captura, los filtros de validez, el cálculo de CRC32 ni la estructura del Parquet. No abre datos de validación ni altera el experimento. Hash actualizado reflejado arriba.

---

## Desviación documentada

**Sesiones: 9 → 7**  
Fecha: 2026-10-23 | Sección afectada: Sección 3 del protocolo  
Motivo: Interrupción operativa en la captura de la sesión 8 (denegación de permiso de ejecución). No hubo acceso a resultados predictivos previo a esta decisión.  
Impacto: Las 15 762 observaciones limpias superan en 2.42× el umbral mínimo de 6 500. El criterio de potencia estadística no se ve comprometido.

---

*Fase 3 cerrada. Siguiente paso: Fase 4 — Evaluación OOS con `scripts/evaluate_models_oos_v3.py` sobre los datos congelados.*
