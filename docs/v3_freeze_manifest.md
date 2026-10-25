# NAVIER V3 — Manifiesto de Congelación Criptográfica

**Fecha de congelación:** 2026-10-22  
**Fase 3 cerrada:** 2026-10-23 — 7 sesiones, 15 762 obs. limpias  
**Estado:** DATOS CAPTURADOS Y CONGELADOS — LISTO PARA EVALUACIÓN OOS (FASE 4)  
**Auditor cuantitativo:** Independiente  

---

## 1. Hashes Criptográficos SHA-256 de los Artefactos Congelados

| Componente | Archivo | Hash SHA-256 |
|---|---|---|
| **Protocolo Científico** | `NAVIER_V3_PROTOCOL.md` | `0183B474253D5B6F50F25ABA7E463A925A4FF5183DA99A3648736DD93095114A` |
| **Pipeline de Features** | `navier_lab/features.py` | `1B642EBFE827E9348F8DED67F9E5F706D0F6599074156094FB73131A2FA853DB` |
| **Esquema y Configuración** | `navier_lab/schema.py` | `A34CEC8A9D57B3BDCF8C5B7E803452B33E288B238CBA2F398C66F0FA8CF80E1A` |
| **Resampleador Causal L2** | `navier_lab/resampler.py` | `220BE7754E5377F69D4539B400435F40A6E96257687237E1AC8CF957E3DE7F35` |
| **Motor de Evaluación OOS** | `scripts/evaluate_models_oos_v3.py` | `52F566F12BC2728EACEBEEF97EBCCE04133E68D3166BCDEDFD9C6D5F7B67BEDB` |
| **Capturador L2** | `scripts/capture_kraken_l2.py` | `D7F01A500F54AC790262AD41806394A8288189E5D31C55F012A57F903C681712` |
| **Suite de Pruebas V3** | `tests/test_features_v3.py` | `9202EB588BAA451C2CB53E8BE6BA25BB18D08A8195A339EAC6F2818074763118` |

> *Nota de integridad:* Estos hashes garantizan la inmutabilidad de las definiciones y el código tras el cierre de las dos observaciones de auditoría (matriz MECE y coherencia dimensional en B++) previo a la recolección de datos independientes. La ausencia de leakage queda demostrada por las 40 pruebas unitarias de causalidad, idempotencia, límites exactos de horizonte y partición exhaustiva de la matriz de decisión.

---

## 2. Entorno de Ejecución

- **Sistema Operativo:** Windows 11
- **Python:** 3.10.9
- **Pytest:** 8.4.2 / 9.1.1
- **Librerías principales:** numpy, pandas, scipy, pyarrow, statsmodels

---

## 3. Estado de la Suite de Pruebas

- **Total de pruebas ejecutadas:** 40
- **Aprobadas:** 40 (100%)
- **Fallidas:** 0
- **Advertencias:** 1 (RuntimeWarning en `test_constant_price_numerical_stress` por división por cero en volatilidad constante nula, esperado y controlado).
