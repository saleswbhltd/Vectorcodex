"""
Step 38 — Tune each engine's score threshold for max F1 / max precision.

For each engine: sweep threshold from 0.4 to 1.0, find the curve. Report
the operating points: (a) max-F1, (b) max-precision-with-recall≥10%,
(c) ultra-strict (precision-first, low recall).
"""

import pandas as pd
import numpy as np
import importlib.util, sys

# Import step 37 to reuse engines
spec = importlib.util.spec_from_file_location("e37", "/home/cmake/Vector/research/37_pivot_engines.py")
e37 = importlib.util.module_from_spec(spec)
sys.modules["e37"] = e37
spec.loader.exec_module(e37)

DATA = "/home/cmake/Vector/research/m5_with_h1.csv.gz"


def main():
    df = pd.read_csv(DATA, index_col=0, parse_dates=True)
    pivots = e37.detect_pivots(df, 20)
    pivot_lookups = {}
    for lbl in ("HH","HL","LH","LL"):
        times = [t for t, x, p in pivots if x == lbl]
        pivot_lookups[lbl] = pd.Series(df.index.isin(times), index=df.index)

    print(f"loaded {len(df):,} bars, ZZ pivots by type:")
    for lbl, m in pivot_lookups.items():
        print(f"  {lbl}: {m.sum()}")

    engines_classes = [e37.BuySwingEngine, e37.BuyPullbackEngine,
                       e37.SellSwingEngine, e37.SellPullbackEngine]
    summary = []

    for cls in engines_classes:
        eng = cls(score_threshold=0.0)   # start permissive — we threshold afterwards
        result = eng.detect(df)
        scores = result["score"]; hard_mask = result["mask"]
        # The hard_mask in step 37 already includes score >= threshold (which is 0 here),
        # so it's just the hard gate. Sweep with multiplied score threshold.
        target = pivot_lookups[eng.target_label]
        print(f"\n{'='*70}\n— {eng.name}  targets {eng.target_label}\n{'='*70}")
        print(f"  hard-gate bars: {int(hard_mask.sum())}  "
              f"(real {eng.target_label} pivots = {int(target.sum())})")
        print(f"{'thr':>5s} {'n':>5s} {'matches':>8s} {'prec':>6s} {'recall':>6s} {'F1':>5s}")

        thresholds = np.linspace(0.40, 1.00, 13)
        best_f1 = {"f1": 0}; best_strict = {"prec": 0}
        for th in thresholds:
            mask = hard_mask & (scores >= th)
            res = eng.score(mask, scores, target, tol=1)
            if res["signals"] == 0: continue
            print(f"  {th:.2f} {res['signals']:>5d} {res['matches']:>8d} "
                  f"{100*res['precision']:>5.1f}% {100*res['recall']:>5.1f}% {res['f1']:.3f}")
            row = {"engine": eng.name, "target": eng.target_label, "threshold": th, **res}
            summary.append(row)
            if res["f1"] > best_f1["f1"]:
                best_f1 = {**row, "f1": res["f1"]}
            if res["precision"] > best_strict["prec"] and res["recall"] >= 0.10:
                best_strict = {**row, "prec": res["precision"]}

        print(f"  ► best F1     : thr={best_f1.get('threshold',0):.2f}  "
              f"prec={100*best_f1.get('precision',0):.1f}%  rec={100*best_f1.get('recall',0):.1f}%")
        print(f"  ► best PREC (rec≥10%): thr={best_strict.get('threshold',0):.2f}  "
              f"prec={100*best_strict.get('precision',0):.1f}%  rec={100*best_strict.get('recall',0):.1f}%")

    pd.DataFrame(summary).to_csv(
        "/home/cmake/Vector/research/engine_threshold_sweep.csv",
        index=False, float_format="%.4f")
    print("\nsaved → engine_threshold_sweep.csv")


if __name__ == "__main__":
    main()
