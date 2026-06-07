"""
Step 17 — Final lever: sweep ZigZag threshold to find the best balance between
entry-lag tax (small thresh = small lag) and pivot quality (large thresh = clean turn).

For each threshold ∈ {5, 8, 10, 12, 15, 20}:
  1. Use the existing pivot detection (already in pivots_threshN.csv)
  2. Apply the G1+G3 trajectory filter (atr14 in [6,11], dist_to_today_low ≤ 80)
     plus G6 confirm_lag ≤ 8 — but confirm_lag is measured in bars, so it scales
     with threshold automatically
  3. Compute MFE/MAE from confirm bar at 60min
  4. Report expectancy with SL=10 trail and OOS
"""

import pandas as pd
import numpy as np

DATA = "/home/cmake/Vector/research/m5_deep.csv.gz"
SPLIT = "2025-07-01"
PIP = 0.0001
LOOKAHEAD = 12  # 60 min


def run_thresh(th):
    df = pd.read_csv(DATA, index_col=0, parse_dates=True)
    piv = pd.read_csv(f"/home/cmake/Vector/research/pivots_thresh{th}.csv",
                      parse_dates=["pivot_time","confirm_time"])
    piv = piv[piv["label"].isin(["HH","HL","LH","LL"])].copy()

    bar_idx = pd.Series(range(len(df)), index=df.index)
    H = df["high"].values; L = df["low"].values; C = df["close"].values
    atr14 = df["atr14_pips"].values
    d2low = df["dist_to_today_low_pips"].values

    rows = []
    for _, p in piv.iterrows():
        if p["confirm_time"] not in bar_idx.index: continue
        if p["pivot_time"]   not in bar_idx.index: continue
        pi = int(bar_idx.loc[p["pivot_time"]])
        ci = int(bar_idx.loc[p["confirm_time"]])
        if ci + LOOKAHEAD >= len(df): continue

        is_high = bool(p["is_high"])
        entry = C[ci]
        # Gates evaluated at pivot bar
        a = atr14[pi]; d = d2low[pi]; lag = p["confirm_lag_bars"]
        g1 = 6 <= a <= 11
        g3 = d <= 80
        g6 = lag <= 8
        passes = g1 and g3 and g6

        # 60-min MFE / MAE from confirm
        mfe = 0.0; mae = 0.0
        for k in range(1, LOOKAHEAD+1):
            j = ci + k
            if is_high:
                fav = (entry - L[j]) / PIP; adv = (H[j] - entry) / PIP
            else:
                fav = (H[j] - entry) / PIP; adv = (entry - L[j]) / PIP
            if fav > mfe: mfe = fav
            if adv > mae: mae = adv

        rows.append({"pivot_time": p["pivot_time"], "passes": passes,
                     "mfe": mfe, "mae": mae,
                     "direction": "SELL" if is_high else "BUY"})

    return pd.DataFrame(rows)


def expectancy(d, sl):
    real = np.where(d["mae"] >= sl, -sl, np.maximum(d["mfe"] - sl, 0))
    return real.mean(), (real > 0).sum(), real.sum()


def main():
    print(f"{'thresh':>6s} {'n':>5s} {'pass':>5s} {'pass%':>6s}  "
          f"{'side':>4s}  {'MFE':>5s}  {'MAE':>5s}  "
          f"{'SL10 net':>8s} {'SL15 net':>8s} {'SL20 net':>8s}  "
          f"{'WR10':>5s}")
    for th in [5, 8, 10, 12, 15, 20, 25]:
        out = run_thresh(th)
        test = out[out["passes"]]
        # split BUY/SELL
        for d in ("SELL", "BUY"):
            te_te = test[test["direction"]==d].copy()
            te_te = te_te[te_te["pivot_time"] >= SPLIT]
            if len(te_te) < 5: continue
            mfe_avg = te_te["mfe"].mean(); mae_avg = te_te["mae"].mean()
            e10, w10, t10 = expectancy(te_te, 10)
            e15, w15, t15 = expectancy(te_te, 15)
            e20, w20, t20 = expectancy(te_te, 20)
            print(f"{th:>4d}p  {len(out):>5d} {len(test):>5d}  "
                  f"{100*len(test)/len(out):>5.1f}%  "
                  f"{d:>4s}  {mfe_avg:>5.1f}  {mae_avg:>5.1f}  "
                  f"{e10:>+8.2f} {e15:>+8.2f} {e20:>+8.2f}  "
                  f"{100*w10/len(te_te):>4.0f}%")


if __name__ == "__main__":
    main()
