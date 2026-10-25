"""Construye notebooks/001_navier_signal_research.ipynb (luego se ejecuta con nbconvert)."""
import nbformat as nbf
from nbformat.v4 import new_notebook, new_markdown_cell as md, new_code_cell as code

cells = []

cells.append(md("""# Notebook 001 — ¿Contienen señal las variables inspiradas en dinámica de fluidos?

> **Regla de oro del proyecto:** *«Si la hipótesis no funciona, el modelo debe demostrarlo, no intentar hacer que funcione.»*

**Pregunta científica.** ¿Pueden variables inspiradas en fluidos (velocidad $u$, $\\partial I/\\partial t$, gradiente y curvatura de liquidez por nivel, un número tipo Reynolds) explicar algo del movimiento de corto plazo que las variables tradicionales (spread, imbalance, OFI, volatilidad, momentum) **no** explican ya?

**Alcance de esta versión (V0.1).** Solo datos **sintéticos con verdad conocida**. El objetivo NO es saber si el mercado real tiene señal (eso es imposible con datos simulados), sino **validar la tubería**: que detecte lo que existe y que *no invente* lo que no existe. Sin LLM, sin redes neuronales, sin descargas, sin trading.

**Cómo está organizado**

| # | Sección | Pregunta que responde |
|---|---|---|
| 1 | Mundos sintéticos + recolector | ¿Cuál es la verdad que conocemos? ¿El pipeline es correcto (sin *look-ahead*, streaming = bloque)? |
| 2 | Comportamiento de las variables | ¿Cómo se distribuyen, cómo se correlacionan, cuánta memoria tienen? |
| 3 | Relación con el retorno futuro | ¿Existe relación? ¿Es monótona? |
| 4 | Significancia | ¿Es estadísticamente significativa (con solapamiento y multiplicidad)? |
| 5 | Información individual | ¿Qué aporta cada variable por sí sola? |
| 6 | Aporte incremental | ¿Navier añade algo **más allá** de lo tradicional? (la pregunta central) |
| 7 | Potencia y falsos positivos | ¿Qué tan grande debe ser una señal para que la veamos? ¿Con qué frecuencia el pipeline inventa señal? |
| 8 | Veredicto y qué está (y no está) validado | |"""))

cells.append(code("""import sys, pathlib, subprocess, time, json, warnings
ROOT = pathlib.Path.cwd().resolve().parent if pathlib.Path.cwd().name == "notebooks" else pathlib.Path.cwd().resolve()
sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd, matplotlib.pyplot as plt
import pyarrow.parquet as pq
from IPython.display import display, Markdown
from navier_lab import synthetic as S, features as F, analysis as A, collector as C, plots as P
from navier_lab.schema import DEFAULT_CONFIG as CFG

pd.set_option("display.width", 200); pd.set_option("display.max_columns", 40); pd.set_option("display.float_format", "{:.4f}".format)
H = CFG.horizon
DATA = ROOT / "data" / "synthetic"
SCEN = list(S.SCENARIOS)
SUMMARY = {}          # se exporta al final a results_summary.json
print(f"Horizonte H = {H} s | ventana máx = {CFG.max_window} s | escenarios: {SCEN}")"""))

# ---------------------------------------------------------------- 1
cells.append(md("""## 1. Tres mundos sintéticos con verdad conocida

Generamos L2 de 10 niveles a 1 s (≈ 27.8 h por mundo, fecha ficticia **2000-01-01** para no confundirla con datos reales). Los *latentes* ocultos son: un flujo lento $f_t$ (se manifiesta como imbalance), una inclinación de liquidez por nivel $\\tau_t$ (gradiente) y volatilidad estocástica con colas pesadas.

| Mundo | Qué determina el retorno futuro | Qué **debe** concluir un pipeline honesto |
|---|---|---|
| **S0_noise** | Nada (ruido puro) | Ninguna variable significativa (salvo el 5 % esperado por azar). |
| **S1_traditional** | Solo $f_t$ (≈ imbalance) | Señales univariadas en variables ligadas a $f$, **incluidas** las Navier correlacionadas con $f$; pero **aporte incremental Navier = 0**. |
| **S2_navier** | $f_t$ + $\\tau_t$ (gradiente) + aceleración del flujo $(f_t-f_{t-5})$ | Detectar el aporte incremental de las variables Navier. |

S1 es el mundo más importante: las variables Navier salen del **mismo libro** y están correlacionadas con las tradicionales. Un mal pipeline las declararía "significativas" por simple colinealidad.

**Recolector / preprocesador.** El L2 crudo se guarda en Parquet (row-groups de 20 000 filas); `ParquetSource` lo lee **por chunks**, `stream_features` calcula variables manteniendo en memoria solo una cola de `max_window + H` filas, y escribe las variables (~16 MB por mundo) también por row-groups. Sustituir por datos reales = cambiar `ParquetSource` por otra fuente que respete el mismo esquema (`navier_lab/schema.py`)."""))

cells.append(code("""t0 = time.time()
paths = S.build_all(DATA, n=100_000, seed=7)                       # L2 crudo + latentes (verdad oculta)
stats_rows = []
for sc, pth in paths.items():
    st = F.run_pipeline(C.ParquetSource(pth), DATA / f"features_{sc}.parquet", CFG)   # streaming por chunks
    stats_rows.append(dict(escenario=sc, filas_raw=100_000, filas_features=st["rows_out"], max_chunk_filas=st["max_chunk_rows"],
                           raw_MB=(DATA / f"raw_{sc}.parquet").stat().st_size / 1e6,
                           features_MB=(DATA / f"features_{sc}.parquet").stat().st_size / 1e6))
display(pd.DataFrame(stats_rows).set_index("escenario"))
print(f"tiempo: {time.time() - t0:.1f} s   (el raw se procesó en chunks de 20 000 filas; nunca se cargó completo)")"""))

cells.append(md("""### 1.1 Pruebas de integridad del pipeline

Antes de mirar cualquier resultado estadístico comprobamos lo que más suele arruinar una investigación de microestructura:
- **Sin look-ahead:** alterar el *futuro* de los datos no cambia ninguna variable en el pasado.
- **El objetivo mira al futuro y las variables no:** el target coincide con $\\log(M_{t+H}/M_t)$ y ninguna variable se le parece.
- **Streaming ≡ bloque:** procesar en chunks (de tamaños arbitrarios) da *exactamente* el mismo resultado que en bloque.
- El validador de datos rechaza libro cruzado, cantidades ≤ 0 y huecos en la malla de 1 s; el re-muestreo evento→1 s toma el último estado del segundo."""))

cells.append(code("""r = subprocess.run([sys.executable, str(ROOT / "tests" / "test_pipeline.py")], capture_output=True, text=True, cwd=ROOT)
print(r.stdout if r.returncode == 0 else r.stdout + r.stderr)
assert r.returncode == 0, "Las pruebas de integridad fallaron: NO continuar."
SUMMARY["integrity_tests_passed"] = True"""))

cells.append(code("""# Cargamos SOLO las variables (no el L2 crudo). Un row-group del crudo se usa únicamente para el gráfico de contexto.
DF = {sc: pd.read_parquet(DATA / f"features_{sc}.parquet") for sc in SCEN}
for d in DF.values():
    for c in d.columns:
        if c not in ("timestamp", "mid"): d[c] = d[c].astype("float64")
raw_chunk = pq.ParquetFile(paths["S2_navier"]).read_row_group(1).to_pandas()   # 20 000 filas
print({sc: d.shape for sc, d in DF.items()})
P.fig_overview(DF["S2_navier"], raw_chunk);"""))

# ---------------------------------------------------------------- 2
cells.append(md("""## 2. ¿Cómo se comportan las variables?

Definiciones **operacionales** (no hay ley física que las respalde; son hipótesis de trabajo):

| Variable | Definición | Grupo |
|---|---|---|
| `u` | pendiente MCO del log-mid (bps) en 5 s → bps/s | Navier |
| `dI_dt` | $[\\bar I_t-\\bar I_{t-5}]/5$ con $\\bar I$ suavizada 3 s | Navier |
| `grad_bid/ask` | pendiente de $V_k/\\bar V$ frente al nivel $k=1..10$, por lado | Navier |
| `curv_bid/ask` | coeficiente cuadrático (polinomio ortogonal) de $V_k/\\bar V$ frente a $k$ | Navier |
| `re_log` | $\\log(1+Re)$, $Re=|u|\\,L/D$; $L$=profundidad del libro (bps), $D$=varianza 1 s (bps²/s) | Navier |
| `imb_full`, `imb_top1`, `ofi_5`, `ret_1/5/30`, `spread_bps`, `depth_log`, `vol60_bps` | tradicionales | trad./básicas |
| `imb_full_lag{2,5,8}` | rezagos de $I$ (control lineal-temporal: baseline **B+**) | control |

**Objetivo:** $y=\\dfrac{\\log(M_{t+H}/M_t)}{\\hat\\sigma_{60}\\sqrt H}$ con $H=10$ s (retorno futuro normalizado por la volatilidad *pasada*; también se guarda en bps).
`grad_asym`, `grad_sym`, `curv_sym` son combinaciones lineales de las anteriores: solo se usan en el análisis univariado."""))

cells.append(code("""desc = DF["S2_navier"][F.FEATURE_COLUMNS + ["y"]].describe(percentiles=[.01, .99]).T
desc["skew"] = DF["S2_navier"][F.FEATURE_COLUMNS + ["y"]].skew(); desc["kurt"] = DF["S2_navier"][F.FEATURE_COLUMNS + ["y"]].kurt()
display(desc[["mean", "std", "1%", "99%", "skew", "kurt"]])
P.fig_distributions(DF["S2_navier"]);"""))

cells.append(code("""P.fig_corr(DF["S2_navier"]);
P.fig_acf(DF["S2_navier"], H);"""))

cells.append(code("""# Colinealidad: factor de inflación de varianza (VIF) del bloque completo de modelos
Xs = DF["S2_navier"][F.MODEL_CPLUS].to_numpy(float); Xs = (Xs - Xs.mean(0)) / Xs.std(0)
vif = pd.Series(np.diag(np.linalg.inv(np.corrcoef(Xs.T))), index=F.MODEL_CPLUS, name="VIF").sort_values(ascending=False)
display(vif.head(8).to_frame())
SUMMARY["max_vif_model"] = float(vif.max())"""))

# ---------------------------------------------------------------- 3
cells.append(md("""## 3. ¿Existe relación entre las variables y el retorno futuro?

Como $y$ es un retorno a 10 s calculado **cada segundo**, observaciones vecinas comparten ~90 % de su ventana: **no son independientes**. Por eso:
- el t-estadístico usa errores **HAC Newey-West** (20 rezagos),
- y verificamos con una **permutación por desplazamiento circular** (se desplaza la variable respecto a $y$; conserva su autocorrelación, rompe la relación; se excluyen desplazamientos < 1000 s),
- con **corrección de multiplicidad** (FDR de Benjamini-Hochberg sobre 24 variables).

Tabla del mundo **S2** y comparación de los tres mundos:"""))

cells.append(code("""UNI = {sc: A.univariate_table(DF[sc], F.FEATURE_COLUMNS, H) for sc in SCEN}
tab = UNI["S2_navier"].copy(); tab["grupo"] = tab.feature.map(P.group_of)
display(tab[["feature", "grupo", "pearson", "spearman", "t_hac", "p_hac", "p_perm", "q_perm"]].sort_values("t_hac", key=abs, ascending=False).reset_index(drop=True))"""))

cells.append(code("""P.fig_forest(UNI);
P.fig_deciles(DF, H);"""))

cells.append(code("""sig = pd.DataFrame({sc: UNI[sc].assign(grupo=UNI[sc].feature.map(P.group_of)).query("q_perm < 0.05").groupby("grupo").size() for sc in SCEN}).reindex(["basic", "trad", "lag", "navier"]).fillna(0).astype(int)
sig.loc["TOTAL"] = sig.sum(); sig["n_vars"] = pd.Series({"basic": 5, "trad": 6, "lag": 3, "navier": 10, "TOTAL": 24})
display(sig.rename_axis("nº de variables con q<5% (FDR)"))
SUMMARY["n_sig_univariate_fdr5"] = sig.loc["TOTAL", SCEN].to_dict()
SUMMARY["n_sig_navier_univariate_fdr5"] = sig.loc["navier", SCEN].to_dict()"""))

# ---------------------------------------------------------------- 4
cells.append(md("""## 4. ¿La relación es estadísticamente significativa? — calibración del propio test

Una relación "significativa" no significa nada si el test está mal calibrado. Lo comprobamos con una hipótesis nula **construida a propósito**: desplazamos circularmente una variable (relación con $y$ destruida) y contamos cuántas veces el test rechaza al 5 %. Debería ser ≈ 5 %. Comparamos el t **ingenuo** (observaciones iid) con el t-**HAC**:"""))

cells.append(code("""y0 = DF["S0_noise"]["y"].to_numpy(float); n = len(y0); rows = []
rng = np.random.default_rng(0)
for f in ["imb_full", "dI_dt", "grad_asym", "u", "ofi_5", "vol60_bps"]:
    x = DF["S0_noise"][f].to_numpy(float)
    cc = A.circular_corr_all_shifts(x, y0); ok = cc[1000:n - 1000]
    t_naive = ok * np.sqrt((n - 2) / (1 - ok ** 2))
    cal = A.calibration_check(x, y0, H, n_shifts=300)
    rows.append(dict(variable=f, rechazo_naive_5pct=np.mean(np.abs(t_naive) > 1.96), rechazo_HAC_5pct=cal["reject_5pct"], sd_t_HAC=cal["t_sd"]))
cal_tab = pd.DataFrame(rows).set_index("variable"); display(cal_tab)
SUMMARY["calibration"] = cal_tab.round(4).to_dict()
fig, cal = P.fig_calibration(DF["S0_noise"]["dI_dt"].to_numpy(float), y0, H)"""))

cells.append(md("""**Lectura.** El t ingenuo rechaza mucho más del 5 % (los retornos solapados y las variables persistentes inflan la significancia). El t-HAC se acerca al 5 % pero puede quedar algo por encima (sd(t) > 1); por eso **no nos basamos en un solo test**: usamos HAC, permutación circular, FDR, y (en la sección 6) validación fuera de muestra con placebo."""))

# ---------------------------------------------------------------- 5
cells.append(md("""## 5. ¿Qué información aporta cada variable individualmente?

Tres lentes distintas, todas **fuera de muestra** o corregidas por su nula:
1. **R² OOS univariado** (walk-forward expansivo, 6 bloques, *purga* de $H$ filas entre train y test).
2. **Información mutua** (captura no linealidad) sobre submuestra **no solapada** (cada $H$ s), menos su valor bajo nula (variable desplazada).
3. **ΔR² OOS al añadir la variable al baseline B+** (aporte *marginal*, controlando por todo lo tradicional).

Se muestra el mundo **S2** (donde hay señal plantada) y, como contraste, S1."""))

cells.append(code("""def info_block(sc):
    d = DF[sc]; y = d["y"].to_numpy(float); spl = A.wf_splits(len(d), K=6, purge=H)
    uo = A.univariate_oos(d, F.FEATURE_COLUMNS, y, spl)
    mi = A.mi_table(d, F.FEATURE_COLUMNS, H)
    a1 = A.add_one_table(d, F.MODEL_BPLUS, F.NAVIER + F.NAVIER_EXTRA[:0], y, spl, H)
    return uo, mi, a1
t0 = time.time(); INFO = {sc: info_block(sc) for sc in ["S1_traditional", "S2_navier"]}; print(f"{time.time() - t0:.0f} s")
uo, mi, a1 = INFO["S2_navier"]
P.fig_information(uo, mi, a1);"""))

cells.append(code("""for sc in ["S1_traditional", "S2_navier"]:
    print(f"\\n>>> {sc}: aporte marginal de cada variable Navier añadida al baseline B+ (ΔR² OOS, DM, q-FDR)")
    display(INFO[sc][2].assign(delta_r2_pct=lambda d: 100 * d.delta_r2).drop(columns="delta_r2").set_index("feature"))"""))

# ---------------------------------------------------------------- 6
cells.append(md("""## 6. ¿Las variables Navier aportan información **adicional** a las tradicionales? (la pregunta central)

Modelos anidados (regresión lineal, sin hiperparámetros que optimizar):

| Modelo | Variables |
|---|---|
| **A** | spread, profundidad, volatilidad |
| **B** | A + imbalance (total y top-1), OFI, momentum 1/5/30 s |
| **B+** | B + rezagos de imbalance ($t-2,5,8$) ← *control estricto:* $\\partial I/\\partial t$ es casi una combinación lineal de $I$ en dos instantes; sin este control cualquier "aporte" de la derivada podría ser solo memoria de $I$ |
| **C+** | B+ + las 7 variables Navier (`u, dI_dt, grad_bid, grad_ask, curv_bid, curv_ask, re_log`) |

La comparación decisiva es **C+ vs B+**. **Criterios de decisión fijados ANTES de ver resultados** (los 4 deben cumplirse, α = 1 %):
1. **Wald-HAC** conjunto de las 7 variables Navier (dado B+): $p<\\alpha$.
2. **Diebold-Mariano** fuera de muestra (C+ vs B+): ΔR² OOS > 0 y $p<\\alpha$.
3. ΔR² OOS > 0 en **≥ 4 de 5** folds.
4. **Placebo**: el ΔR² OOS real supera al percentil $1-\\alpha$ del obtenido con el bloque Navier **desplazado circularmente** (150 desplazamientos).

Es deliberadamente conservador: prefiere descartar una señal real pequeña antes que inventar una falsa."""))

cells.append(code("""t0 = time.time()
RES = {sc: A.nested_comparison(DF[sc], H, K=6, n_shifts=150, seed=1) for sc in SCEN}
VER = {sc: A.verdict(RES[sc]) for sc in SCEN}
print(f"{time.time() - t0:.0f} s")
tbl = pd.DataFrame({sc: {**{f"R² OOS {k.split()[0]} (%)": 100 * v for k, v in RES[sc]["r2"].items()},
                         "ΔR² OOS (C+ − B+) (%)": 100 * RES[sc]["delta_r2"], "DM t": RES[sc]["dm"]["t"], "DM p": RES[sc]["dm"]["p"],
                         "Wald χ²(7)": RES[sc]["wald"]["chi2"], "Wald p": RES[sc]["wald"]["p"], "placebo p": RES[sc]["p_placebo"],
                         "folds con ΔR²>0 (de 5)": int((RES[sc]["fold_delta"] > 0).sum()),
                         "hit-rate B+": RES[sc]["hit_rate_base"], "hit-rate C+": RES[sc]["hit_rate_alt"]} for sc in SCEN})
display(tbl)"""))

cells.append(code("""P.fig_nested(RES);
ver_tab = pd.DataFrame(VER).T[["c1_wald", "c2_dm", "c3_folds", "c4_placebo", "signal"]]
ver_tab.columns = ["1 Wald p<1%", "2 DM p<1% y ΔR²>0", "3 ≥4/5 folds", "4 placebo p<1%", "SEÑAL (los 4)"]
display(ver_tab)
for sc in SCEN: print(f"{sc:16s} -> {VER[sc]['text']}")
SUMMARY["nested"] = {sc: dict(delta_r2_pct=100 * RES[sc]["delta_r2"], dm_p=RES[sc]["dm"]["p"], wald_p=RES[sc]["wald"]["p"], placebo_p=RES[sc]["p_placebo"],
                              folds_pos=int((RES[sc]["fold_delta"] > 0).sum()), r2_oos_pct={k: 100 * v for k, v in RES[sc]["r2"].items()},
                              verdict=VER[sc]) for sc in SCEN}"""))

# ---------------------------------------------------------------- 7
cells.append(md("""## 7. Potencia y falsos positivos: ¿cuánta señal necesitamos y cuántas veces inventamos una?

Un pipeline que dice "no hay señal" sólo es informativo si sabemos **qué tamaño de señal habría visto**. Dos controles:

**(a) Curva de potencia.** Repetimos el mundo S2 escalando la señal plantada (0 %, 25 %, 50 %, 75 %, 100 %; el 0 % es S1 con la misma semilla).

**(b) Robustez al horizonte** ($H=5,10,30$ s) en S1 (debe seguir sin aporte) y S2 (debe seguir detectándolo).

**(c) Monte Carlo de falsos positivos:** 20 semillas nuevas de S0 y de S1; el veredicto completo debería salir "señal" ≈ 0 veces."""))

cells.append(code("""t0 = time.time(); rows = []
for frac in [0.0, 0.25, 0.5, 0.75, 1.0]:
    raw, _ = S.generate("S2_navier", n=100_000, seed=7, navier_scale=frac)
    ch = (raw.iloc[i:i + 20_000] for i in range(0, len(raw), 20_000))
    d = pd.concat(list(F.stream_features(ch, CFG)), ignore_index=True)
    r = A.nested_comparison(d, H, n_shifts=120, seed=2); v = A.verdict(r)
    rows.append(dict(fraction=frac, delta_r2=r["delta_r2"], wald_p=r["wald"]["p"], dm_p=r["dm"]["p"], p_placebo=r["p_placebo"],
                     folds_pos=int((r["fold_delta"] > 0).sum()), signal=v["signal"]))
POWER = pd.DataFrame(rows); print(f"{time.time() - t0:.0f} s")
display(POWER.assign(delta_r2_pct=100 * POWER.delta_r2).drop(columns="delta_r2").set_index("fraction"))
P.fig_power(POWER);
SUMMARY["power"] = POWER.to_dict(orient="list")"""))

cells.append(code("""t0 = time.time(); rows = []
for sc in ["S1_traditional", "S2_navier"]:
    for h in [5, 10, 30]:
        d = A.retarget(DF[sc], h)
        r = A.nested_comparison(d, h, n_shifts=100, seed=3); v = A.verdict(r)
        rows.append(dict(escenario=sc, H=h, delta_r2_pct=100 * r["delta_r2"], wald_p=r["wald"]["p"], dm_p=r["dm"]["p"],
                         p_placebo=r["p_placebo"], folds_pos=int((r["fold_delta"] > 0).sum()), señal=v["signal"]))
HOR = pd.DataFrame(rows); print(f"{time.time() - t0:.0f} s")
display(HOR.set_index(["escenario", "H"]))
SUMMARY["horizons"] = HOR.to_dict(orient="records")"""))

cells.append(code("""mc_path = DATA / "mc_false_positive.csv"
if mc_path.exists():
    MC = pd.read_csv(mc_path)
    print(f"{len(MC)} corridas ({MC.groupby('scenario').size().to_dict()}), cada una con semilla nueva. (Regenerar: python scripts/monte_carlo_fp.py 20)")
    P.fig_mc(MC)
    fp = MC.groupby("scenario")[["c1_wald", "c2_dm", "c3_folds", "c4_placebo", "signal"]].agg(["sum", "count"])
    display(MC.groupby("scenario")[["c1_wald", "c2_dm", "c3_folds", "c4_placebo", "signal"]].sum().rename(columns={"signal": "TODOS (falso positivo)"}).assign(corridas=MC.groupby("scenario").size()))
    SUMMARY["mc_false_positive"] = {"n_runs": MC.groupby("scenario").size().to_dict(), "signal_true": MC.groupby("scenario")["signal"].sum().to_dict(),
                                    "wald_p_lt_1pct": MC.groupby("scenario")["c1_wald"].sum().to_dict()}
else:
    print("Falta data/synthetic/mc_false_positive.csv — ejecutar scripts/monte_carlo_fp.py")"""))

# placeholder for interpretive sections (filled after inspecting results)
cells.append(md("@@INTERPRETATION@@"))

cells.append(code("""(ROOT / "results").mkdir(exist_ok=True)
def _clean(o):
    if isinstance(o, dict): return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)): return [_clean(v) for v in o]
    if isinstance(o, (np.floating, np.integer, np.bool_)): return o.item()
    return o
json.dump(_clean(SUMMARY), open(ROOT / "results" / "results_summary.json", "w"), indent=2, ensure_ascii=False)
UNI["S2_navier"].to_csv(ROOT / "results" / "univariate_S2.csv", index=False)
pd.concat({sc: UNI[sc] for sc in SCEN}).to_csv(ROOT / "results" / "univariate_all_scenarios.csv")
print("Resultados exportados a results/")"""))

nb = new_notebook(cells=cells, metadata={"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                                         "language_info": {"name": "python"}})
import sys
interp = open("notebooks/_interpretation.md").read() if len(sys.argv) > 1 else "*(interpretación pendiente)*"
for c in nb.cells:
    if c.cell_type == "markdown" and c.source == "@@INTERPRETATION@@":
        c.source = interp
nbf.write(nb, "notebooks/001_navier_signal_research.ipynb")
print("notebook escrito")
