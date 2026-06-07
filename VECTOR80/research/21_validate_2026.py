"""
Step 21 — Pure OOS validation on 2026 EURUSD M5.

This dataset was NOT seen during rule development. The rule was derived from
2025 data. If the rule still works here, it's a real signal — if it doesn't,
we have a regime-overfit problem.

Pipeline:
  1. Detect pivots on 2026 M5 at 25-pip threshold (the best from step 17)
  2. Apply G1+G3+G6 trajectory filter
  3. Compute MFE/MAE from CONFIRM bar over 60 min
  4. Report expectancy at SL=10/15/20 — same metrics as step 17
"""

import pandas as pd
import numpy as np

DATA = "/home/cmake/Vector/research/m5_2026_deep.csv.gz"
PIP = 0.0001
LOOKAHEAD = 12


def detect_pivots(df, thresh_pips):
    thresh = thresh_pips * PIP
    h = df["high"].values; l = df["low"].values; t = df.index.values
    n = len(df)
    direction_up = h[1] >= h[0]
    ext = h[1] if direction_up else l[1]
    ext_i = 1
    out = []
    for i in range(2, n):
        if direction_up:
            if h[i] > ext: ext, ext_i = h[i], i
            elif l[i] <= ext - thresh:
                out.append((t[ext_i], t[i], ext, True, ext_i, i))
                direction_up = False; ext, ext_i = l[i], i
        else:
            if l[i] < ext: ext, ext_i = l[i], i
            elif h[i] >= ext + thresh:
                out.append((t[ext_i], t[i], ext, False, ext_i, i))
                direction_up = True; ext, ext_i = h[i], i
    return pd.DataFrame(out, columns=["pivot_time","confirm_time","price","is_high","pi","ci"])


def main():
    df = pd.read_csv(DATA, index_col=0, parse_dates=True)
    print(f"loaded {len(df):,} bars, range: {df.index[0]} → {df.index[-1]}")
    days = (df.index[-1] - df.index[0]).total_seconds() / 86400
    print(f"days covered: {days:.0f}")

    for thresh in [15, 20, 25, 30]:
        print(f"\n{'='*78}\nTHRESHOLD = {thresh} pips\n{'='*78}")
        piv = detect_pivots(df, thresh)
        piv["confirm_lag"] = ((piv["confirm_time"] - piv["pivot_time"])
                               .dt.total_seconds() / 300).astype(int)
        print(f"  pivots: {len(piv)}  ({len(piv)/days:.2f}/day)")

        H = df["high"].values; L = df["low"].values; C = df["close"].values
        atr14 = df["atr14_pips"].values
        d2low = df["dist_to_today_low_pips"].values

        rows = []
        for _, p in piv.iterrows():
            pi = int(p["pi"]); ci = int(p["ci"])
            if ci + LOOKAHEAD >= len(df): continue
            is_high = bool(p["is_high"])
            entry = C[ci]
            # Gates at PIVOT bar
            g1 = 6 <= atr14[pi] <= 11
            g3 = d2low[pi] <= 80
            g6 = p["confirm_lag"] <= 8
            passes = g1 and g3 and g6
            mfe = 0.0; mae = 0.0
            for k in range(1, LOOKAHEAD + 1):
                j = ci + k
                if is_high:
                    fav = (entry - L[j])/PIP; adv = (H[j] - entry)/PIP
                else:
                    fav = (H[j] - entry)/PIP; adv = (entry - L[j])/PIP
                if fav > mfe: mfe = fav
                if adv > mae: mae = adv
            rows.append({"direction": "SELL" if is_high else "BUY",
                         "passes": passes, "mfe": mfe, "mae": mae,
                         "atr14_piv": atr14[pi], "d2low_piv": d2low[pi],
                         "confirm_lag": p["confirm_lag"]})

        out = pd.DataFrame(rows)
        # Headline: filtered trades
        for d in ("SELL", "BUY"):
            sub = out[(out["direction"]==d) & out["passes"]]
            base = out[out["direction"]==d]
            if len(sub) == 0: continue
            print(f"\n  {d}:  baseline n={len(base)}  filtered n={len(sub)} "
                  f"({100*len(sub)/len(base):.1f}% pass rate)")
            mfe = sub["mfe"]; mae = sub["mae"]
            print(f"    MFE avg={mfe.mean():.1f} (med {mfe.median():.1f}, "
                  f"p75 {mfe.quantile(0.75):.1f})  "
                  f"MAE avg={mae.mean():.1f} (med {mae.median():.1f}, "
                  f"p75 {mae.quantile(0.75):.1f})")
            for sl in [10, 15, 20]:
                real = np.where(mae >= sl, -sl, np.maximum(mfe - sl, 0))
                wins = (real > 0).sum()
                print(f"    SL={sl:2d} trail: avg net = {real.mean():+5.2f}  "
                      f"WR={100*wins/len(sub):.0f}%  total={real.sum():+5.0f} pips")


if __name__ == "__main__":
    main()
