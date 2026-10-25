"""Monte Carlo de FALSOS POSITIVOS: repite S0 y S1 con distintas semillas y aplica el veredicto completo.
Guarda data/synthetic/mc_false_positive.csv  (tarda varios minutos; el notebook solo lo lee)."""
import sys, pathlib, time
ROOT = pathlib.Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
import numpy as np, pandas as pd
from navier_lab import synthetic as S, features as F, analysis as A

H, N_SEEDS = 10, int(sys.argv[1]) if len(sys.argv) > 1 else 20
out_csv = ROOT / "data/synthetic/mc_false_positive.csv"
rows = pd.read_csv(out_csv).to_dict("records") if out_csv.exists() else []   # reanudable
done = {(r["scenario"], r["seed"]) for r in rows}
TIME_BUDGET = float(sys.argv[2]) if len(sys.argv) > 2 else 1e9
t_start = time.time()
for name in ["S0_noise", "S1_traditional"]:
    for seed in range(100, 100 + N_SEEDS):
        if (name, seed) in done or time.time() - t_start > TIME_BUDGET:
            continue
        raw, _ = S.generate(name, n=100_000, seed=seed)
        chunks = (raw.iloc[i:i + 20000] for i in range(0, len(raw), 20000))
        df = pd.concat(list(F.stream_features(chunks)), ignore_index=True)
        res = A.nested_comparison(df, H, n_shifts=100, seed=seed)
        v = A.verdict(res)
        rows.append(dict(scenario=name, seed=seed, delta_r2=res["delta_r2"], wald_p=res["wald"]["p"], dm_p=res["dm"]["p"],
                         p_placebo=res["p_placebo"], folds_pos=int((res["fold_delta"] > 0).sum()), **{k: v[k] for k in ["c1_wald","c2_dm","c3_folds","c4_placebo","signal"]}))
        pd.DataFrame(rows).to_csv(ROOT / "data/synthetic/mc_false_positive.csv", index=False)
        print(name, seed, rows[-1]["signal"], round(rows[-1]["wald_p"], 3), flush=True)
