"""Estadística del Notebook 001.

Principios
----------
* Los retornos futuros a H s se SOLAPAN => las observaciones NO son independientes.
  Toda inferencia usa (a) errores HAC Newey-West con lags >= 2H y (b) permutación por
  DESPLAZAMIENTO CIRCULAR (rompe la relación x-y, conserva la autocorrelación de x).
* Validación fuera de muestra: walk-forward expansivo con PURGA de H filas entre train y test.
* Comparaciones anidadas (A < B < B+ < B+Navier) con test Diebold-Mariano, Wald-HAC y placebo.
* Los criterios de decisión se fijan ANTES de mirar resultados (ver `verdict`).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from . import features as F

# ------------------------------------------------------------------ inferencia univariada
def nw_lrv(s: np.ndarray, lags: int) -> float:
    """Varianza de largo plazo (Newey-West, Bartlett) de la SUMA de s."""
    v = float(s @ s)
    for j in range(1, lags + 1):
        v += 2 * (1 - j / (lags + 1)) * float(s[j:] @ s[:-j])
    return v


def _std(a: np.ndarray) -> np.ndarray:
    return (a - a.mean()) / a.std()


def univ_hac(x: np.ndarray, y: np.ndarray, lags: int) -> tuple[float, float, float]:
    """Regresión y~x (ambas estandarizadas): devuelve (beta=corr, t_HAC, p)."""
    xs, ys = _std(x), _std(y)
    xx = float(xs @ xs)
    b = float(xs @ ys) / xx
    s = xs * (ys - b * xs)
    se = np.sqrt(nw_lrv(s, lags)) / xx
    t = b / se
    return b, t, 2 * stats.norm.sf(abs(t))


def circular_corr_all_shifts(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """corr(x desplazada s, y) para TODOS los s=0..n-1 vía FFT."""
    n = len(x)
    xs, ys = _std(x), _std(y)
    cc = np.fft.irfft(np.conj(np.fft.rfft(ys)) * np.fft.rfft(xs), n=n) / n
    return cc


def perm_p_circular(x: np.ndarray, y: np.ndarray, excl: int = 1000) -> float:
    """p-valor por desplazamiento circular, excluyendo |s|<excl (dependencia local)."""
    n = len(x)
    cc = circular_corr_all_shifts(x, y)
    obs = cc[0]
    idx = np.arange(n)
    ok = (idx >= excl) & (idx <= n - excl)
    null = cc[ok]
    return float((1 + np.sum(np.abs(null) >= abs(obs))) / (1 + len(null)))


def bh_adjust(p: np.ndarray) -> np.ndarray:
    """Benjamini-Hochberg (q-values)."""
    p = np.asarray(p, float)
    n = len(p)
    order = np.argsort(p)
    ranked = p[order] * n / (np.arange(n) + 1)
    q = np.minimum.accumulate(ranked[::-1])[::-1]
    out = np.empty(n)
    out[order] = np.minimum(q, 1)
    return out


def _rank_u(a: np.ndarray) -> np.ndarray:
    return stats.rankdata(a) / len(a)


def univariate_table(df: pd.DataFrame, feats: list[str], H: int, target: str = F.TARGET,
                     excl: int = 1000) -> pd.DataFrame:
    y = df[target].to_numpy(float)
    rows = []
    for f in feats:
        x = df[f].to_numpy(float)
        b, t, p = univ_hac(x, y, 2 * H)
        pp = perm_p_circular(x, y, excl)
        xr, yr = _rank_u(x), _rank_u(y)
        br, tr_, pr = univ_hac(xr, yr, 2 * H)
        ppr = perm_p_circular(xr, yr, excl)
        rows.append(dict(feature=f, pearson=b, t_hac=t, p_hac=p, p_perm=pp,
                         spearman=br, t_hac_rank=tr_, p_perm_rank=ppr))
    out = pd.DataFrame(rows)
    out["q_perm"] = bh_adjust(out["p_perm"].to_numpy())       # corrección por multiplicidad (FDR)
    out["q_perm_rank"] = bh_adjust(out["p_perm_rank"].to_numpy())
    return out


def decile_table(df: pd.DataFrame, feat: str, H: int, nb: int = 10, target: str = F.TARGET) -> pd.DataFrame:
    x = df[feat].to_numpy(float)
    y = df[target].to_numpy(float)
    bins = pd.qcut(x, nb, labels=False, duplicates="drop")
    rows = []
    for b in np.unique(bins):
        ind = (bins == b).astype(float)
        m = float((ind * y).sum() / ind.sum())
        s = ind * (y - m)
        se = np.sqrt(nw_lrv(s, 2 * H)) / ind.sum()
        rows.append(dict(bin=int(b) + 1, mean_y=m, se=se, n=int(ind.sum()), x_mid=float(np.median(x[bins == b]))))
    return pd.DataFrame(rows)


def calibration_check(x: np.ndarray, y: np.ndarray, H: int, n_shifts: int = 400, excl: int = 1000,
                      seed: int = 0) -> dict:
    """¿El t-HAC está bien calibrado? Con x desplazada circularmente (nula por construcción)
    la tasa de rechazo al 5% debería rondar 5%."""
    rng = np.random.default_rng(seed)
    n = len(x)
    shifts = rng.integers(excl, n - excl, n_shifts)
    ts = np.array([univ_hac(np.roll(x, int(s)), y, 2 * H)[1] for s in shifts])
    return dict(reject_5pct=float(np.mean(np.abs(ts) > 1.96)), t_sd=float(ts.std()), t_values=ts)


# ------------------------------------------------------------------ walk-forward
def wf_splits(n: int, K: int = 6, purge: int = 10) -> list[tuple[np.ndarray, np.ndarray]]:
    edges = np.linspace(0, n, K + 1).astype(int)
    out = []
    for i in range(1, K):
        te = np.arange(edges[i], edges[i + 1])
        tr = np.arange(0, edges[i] - purge)
        out.append((tr, te))
    return out


def _fit_ols(Xtr: np.ndarray, ytr: np.ndarray, ridge: float = 1e-6) -> np.ndarray:
    A = np.c_[np.ones(len(Xtr)), Xtr]
    G = A.T @ A
    G[1:, 1:] += ridge * len(Xtr) * np.eye(A.shape[1] - 1)
    return np.linalg.solve(G, A.T @ ytr)


def wf_predict(X: np.ndarray, y: np.ndarray, splits, clip: float = 5.0) -> np.ndarray:
    """OLS con estandarización y recorte (+-clip sd) estimados SOLO con train de cada fold."""
    pred = np.full(len(y), np.nan)
    for tr, te in splits:
        mu, sd = X[tr].mean(0), X[tr].std(0) + 1e-12
        Xtr = np.clip((X[tr] - mu) / sd, -clip, clip)
        Xte = np.clip((X[te] - mu) / sd, -clip, clip)
        b = _fit_ols(Xtr, y[tr])
        pred[te] = b[0] + Xte @ b[1:]
    return pred


def oos_r2(y: np.ndarray, pred: np.ndarray, splits) -> tuple[float, list[float]]:
    """R2 OOS vs. benchmark = media del train de cada fold. Devuelve (global, por fold)."""
    sse = sst = 0.0
    per = []
    for tr, te in splits:
        m = y[tr].mean()
        e2 = float(np.sum((y[te] - pred[te]) ** 2))
        t2 = float(np.sum((y[te] - m) ** 2))
        per.append(1 - e2 / t2)
        sse += e2
        sst += t2
    return 1 - sse / sst, per


def dm_test(y, p_base, p_alt, splits, lags: int) -> dict:
    """Diebold-Mariano (pérdida cuadrática). d>0 => el modelo alternativo es mejor."""
    te = np.concatenate([t for _, t in splits])
    d = (y[te] - p_base[te]) ** 2 - (y[te] - p_alt[te]) ** 2
    dm = d.mean()
    se = np.sqrt(nw_lrv(d - dm, lags)) / len(d)
    t = dm / se
    return dict(mean_diff=float(dm), t=float(t), p=float(2 * stats.norm.sf(abs(t))))


def wald_hac(y: np.ndarray, X_base: np.ndarray, X_extra: np.ndarray, lags: int) -> dict:
    """Test de Wald conjunto (errores HAC) de que los coeficientes de X_extra son 0, en la muestra completa."""
    import statsmodels.api as sm
    Xs = np.c_[X_base, X_extra]
    Xs = (Xs - Xs.mean(0)) / Xs.std(0)
    Xs = np.clip(Xs, -5, 5)
    res = sm.OLS(y, sm.add_constant(Xs)).fit(cov_type="HAC", cov_kwds=dict(maxlags=lags))
    k0, k1 = X_base.shape[1], X_extra.shape[1]
    R = np.zeros((k1, 1 + k0 + k1))
    R[np.arange(k1), 1 + k0 + np.arange(k1)] = 1
    w = res.wald_test(R, use_f=False, scalar=True)
    return dict(chi2=float(w.statistic), df=int(k1), p=float(w.pvalue),
                coefs=dict(zip(range(k1), res.params[1 + k0:])), tvals=res.tvalues[1 + k0:])


def placebo_delta_r2(X_base, X_extra, y, splits, base_r2: float, n_shifts: int = 150,
                     excl: int = 1000, seed: int = 0) -> np.ndarray:
    """Distribución nula del aporte OOS de X_extra: se desplaza circularmente el BLOQUE X_extra
    (conserva su estructura interna y autocorrelación; rompe su relación con y)."""
    rng = np.random.default_rng(seed)
    n = len(y)
    out = []
    for s in rng.integers(excl, n - excl, n_shifts):
        Xp = np.c_[X_base, np.roll(X_extra, int(s), axis=0)]
        r2, _ = oos_r2(y, wf_predict(Xp, y, splits), splits)
        out.append(r2 - base_r2)
    return np.array(out)


def hit_rate(y, pred, splits) -> float:
    te = np.concatenate([t for _, t in splits])
    return float(np.mean(np.sign(pred[te]) == np.sign(y[te])))


# ------------------------------------------------------------------ información individual
def univariate_oos(df, feats, y, splits) -> pd.DataFrame:
    rows = []
    for f in feats:
        p = wf_predict(df[[f]].to_numpy(float), y, splits)
        r2, per = oos_r2(y, p, splits)
        rows.append(dict(feature=f, oos_r2=r2, folds_pos=int(np.sum(np.array(per) > 0))))
    return pd.DataFrame(rows)


def add_one_table(df, base_feats, cand_feats, y, splits, H) -> pd.DataFrame:
    Xb = df[base_feats].to_numpy(float)
    pb = wf_predict(Xb, y, splits)
    r2b, _ = oos_r2(y, pb, splits)
    rows = []
    for f in cand_feats:
        Xa = np.c_[Xb, df[[f]].to_numpy(float)]
        pa = wf_predict(Xa, y, splits)
        r2a, per = oos_r2(y, pa, splits)
        dm = dm_test(y, pb, pa, splits, 2 * H)
        rows.append(dict(feature=f, delta_r2=r2a - r2b, dm_t=dm["t"], dm_p=dm["p"]))
    out = pd.DataFrame(rows)
    out["q_dm"] = bh_adjust(out["dm_p"].to_numpy())
    return out


def mi_table(df, feats, H, target=F.TARGET, n_null: int = 4, seed: int = 0) -> pd.DataFrame:
    """Información mutua (no lineal) sobre submuestra NO solapada (cada H filas) vs. nula por desplazamiento."""
    from sklearn.feature_selection import mutual_info_regression
    rng = np.random.default_rng(seed)
    d = df.iloc[::H]
    y = d[target].to_numpy(float)
    n = len(d)
    rows = []
    for f in feats:
        x = d[[f]].to_numpy(float)
        mi = mutual_info_regression(x, y, n_neighbors=5, random_state=0)[0]
        nulls = [mutual_info_regression(np.roll(x, int(s), axis=0), y, n_neighbors=5, random_state=0)[0]
                 for s in rng.integers(n // 10, n - n // 10, n_null)]
        rows.append(dict(feature=f, mi=mi, mi_null=np.mean(nulls), mi_null_sd=np.std(nulls, ddof=1)))
    out = pd.DataFrame(rows)
    out["mi_excess"] = out["mi"] - out["mi_null"]
    return out


# ------------------------------------------------------------------ comparación anidada + veredicto
MODELS = {
    "A  (basics)": F.MODEL_A,
    "B  (+tradicionales)": F.MODEL_B,
    "B+ (+rezagos de I)": F.MODEL_BPLUS,
    "C  (B+Navier)": F.MODEL_C,
    "C+ (B+ +Navier)": F.MODEL_CPLUS,
}


def nested_comparison(df: pd.DataFrame, H: int, K: int = 6, n_shifts: int = 150, seed: int = 0,
                      target: str = F.TARGET) -> dict:
    y = df[target].to_numpy(float)
    splits = wf_splits(len(df), K=K, purge=H)
    preds, r2, per = {}, {}, {}
    for name, cols in MODELS.items():
        preds[name] = wf_predict(df[cols].to_numpy(float), y, splits)
        r2[name], per[name] = oos_r2(y, preds[name], splits)
    base, alt = "B+ (+rezagos de I)", "C+ (B+ +Navier)"
    dm = dm_test(y, preds[base], preds[alt], splits, 2 * H)
    Xb = df[F.MODEL_BPLUS].to_numpy(float)
    Xn = df[F.NAVIER].to_numpy(float)
    wald = wald_hac(y, Xb, Xn, 2 * H)
    plc = placebo_delta_r2(Xb, Xn, y, splits, r2[base], n_shifts=n_shifts, seed=seed)
    d_act = r2[alt] - r2[base]
    p_plc = float((1 + np.sum(plc >= d_act)) / (1 + len(plc)))
    fold_delta = np.array(per[alt]) - np.array(per[base])
    return dict(r2=r2, per_fold=per, delta_r2=d_act, dm=dm, wald=wald, placebo=plc, p_placebo=p_plc,
                fold_delta=fold_delta, hit_rate_alt=hit_rate(y, preds[alt], splits),
                hit_rate_base=hit_rate(y, preds[base], splits), splits=splits)


def verdict(res: dict, alpha: float = 0.01) -> dict:
    """CRITERIOS PRE-REGISTRADOS (fijados antes de ver resultados). Las 4 deben cumplirse:
       1) Wald-HAC conjunto de las 7 variables Navier (dado B+) con p < alpha
       2) DM (C+ vs B+) con delta R2_OOS > 0 y p < alpha
       3) delta R2 por fold > 0 en al menos 4 de 5 folds
       4) delta R2_OOS real mayor que el percentil (1-alpha) de la distribución placebo (p_placebo < alpha)
    """
    c1 = res["wald"]["p"] < alpha
    c2 = (res["delta_r2"] > 0) and (res["dm"]["p"] < alpha)
    c3 = int(np.sum(res["fold_delta"] > 0)) >= 4
    c4 = res["p_placebo"] < alpha
    ok = bool(c1 and c2 and c3 and c4)
    return dict(c1_wald=bool(c1), c2_dm=bool(c2), c3_folds=bool(c3), c4_placebo=bool(c4), signal=ok,
                text="SEÑAL INCREMENTAL DETECTADA (candidata a Notebook 002)" if ok
                else "SIN EVIDENCIA de señal incremental Navier -> NO se avanza con esta hipótesis tal cual")


def retarget(df: pd.DataFrame, h: int) -> pd.DataFrame:
    """Recalcula el objetivo para otro horizonte h a partir de mid (para robustez). Descarta las últimas h filas."""
    d = df.copy()
    lm = np.log(d["mid"].to_numpy(float)) * 1e4
    fwd = pd.Series(lm).shift(-h).to_numpy() - lm
    d[F.TARGET_BPS] = fwd
    d[F.TARGET] = fwd / (d["vol60_bps"].to_numpy(float) * np.sqrt(h))
    return d.dropna(subset=[F.TARGET]).reset_index(drop=True)
