"""
Step 19 — Quantify the value of earlier entry (i.e. tick / M1 data).

Core insight: the 25-pip retracement confirmation kills our edge. Tick or M1
data could let us detect the pivot turn BEFORE the full 25-pip retracement
completes — e.g. at 5, 10, or 15 pips of retracement instead of 25.

Simulation: for each pivot in the dataset, instead of entering at the bar where
the 25-pip threshold flipped, "rewind" the entry to N pips earlier (closer to
the actual pivot). Compute realistic MFE/MAE from THAT earlier entry and
report what changes.

We don't have M1 / tick data yet, so we simulate by assuming an oracle that
gives us perfect early-confirm at N pips of retracement. The result is an
UPPER BOUND on what tick-level detection could deliver.
"""

import pandas as pd
import numpy as np

DATA   = "/home/cmake/Vector/research/m5_deep.csv.gz"
PIVOTS = "/home/cmake/Vector/research/pivots_thresh15.csv"
SPLIT  = "2025-07-01"
PIP    = 0.0001
LOOKAHEAD_BARS = 12   # 60 min


def realistic_mfe_mae_at_offset(df, piv, retrace_pips):
    """
    For each pivot: walk forward from PIVOT BAR until price has retraced
    `retrace_pips` from the pivot extreme. That's our 'early-confirm' entry.
    Then compute MFE/MAE over LOOKAHEAD_BARS more bars.
    """
    bar_idx = pd.Series(range(len(df)), index=df.index)
    H = df["high"].values
    L = df["low"].values
    C = df["close"].values
    atr14 = df["atr14_pips"].values
    d2low = df["dist_to_today_low_pips"].values

    rows = []
    for _, p in piv.iterrows():
        if p["pivot_time"] not in bar_idx.index: continue
        pi = int(bar_idx.loc[p["pivot_time"]])
        is_high = bool(p["is_high"])
        pivot_px = p["price"]
        trigger = pivot_px - retrace_pips * PIP if is_high else pivot_px + retrace_pips * PIP

        # Find first bar at or after PIVOT BAR where price crosses the trigger
        ci = None
        for k in range(0, 30):                # max 30 bars to confirm
            j = pi + k
            if j >= len(df): break
            if is_high and L[j] <= trigger:
                ci = j; break
            if (not is_high) and H[j] >= trigger:
                ci = j; break
        if ci is None: continue
        if ci + LOOKAHEAD_BARS >= len(df): continue

        entry = C[ci]                          # enter at close of the bar that crossed
        mfe = 0.0; mae = 0.0
        for k in range(1, LOOKAHEAD_BARS + 1):
            j = ci + k
            if is_high:
                fav = (entry - L[j]) / PIP; adv = (H[j] - entry) / PIP
            else:
                fav = (H[j] - entry) / PIP; adv = (entry - L[j]) / PIP
            if fav > mfe: mfe = fav
            if adv > mae: mae = adv
        rows.append({"pivot_time": p["pivot_time"],
                     "direction": "SELL" if is_high else "BUY",
                     "atr14_piv": atr14[pi],
                     "d2low_piv": d2low[pi],
                     "early_lag_bars": ci - pi,
                     "mfe": mfe, "mae": mae})
    return pd.DataFrame(rows)


def apply_filter(df):
    g1 = df["atr14_piv"].between(6, 11)
    g3 = df["d2low_piv"] <= 80
    g6 = df["early_lag_bars"] <= 8
    return df[g1 & g3 & g6]


def main():
    df  = pd.read_csv(DATA, index_col=0, parse_dates=True)
    # Use the 25-pip pivot set as base (the trajectory analysis recommended it)
    piv = pd.read_csv("/home/cmake/Vector/research/pivots_thresh25.csv",
                      parse_dates=["pivot_time","confirm_time"])
    piv = piv[piv["label"].isin(["HH","HL","LH","LL"])].copy()
    print(f"base: {len(piv)} pivots at 25-pip threshold")

    SCENARIOS = [
        ("perfect-oracle entry @ pivot",  0),
        ("ultra-early @ 2 pip retracement (TICK)", 2),
        ("early @ 5 pip retracement (TICK/M1)", 5),
        ("M1-driven @ 10 pip retracement",  10),
        ("standard @ 15 pip retracement",  15),
        ("standard @ 20 pip retracement",  20),
        ("REAL today: 25 pip retracement (M5 only)", 25),
    ]

    print(f"\n{'scenario':45s}  {'side':5s}  {'n_te':5s}  {'MFE':>5s}  {'MAE':>5s}  "
          f"{'SL10 net':>8s}  {'SL15 net':>8s}  {'WR_10':>5s}")
    for label, rp in SCENARIOS:
        out = realistic_mfe_mae_at_offset(df, piv, rp)
        out = apply_filter(out)
        # OOS only
        out = out[out["pivot_time"] >= SPLIT]
        for d in ("SELL", "BUY"):
            sub = out[out["direction"]==d]
            if len(sub) < 5: continue
            mfe = sub["mfe"]; mae = sub["mae"]
            for sl in [10, 15]:
                real = np.where(mae >= sl, -sl, np.maximum(mfe - sl, 0))
                if sl == 10:
                    e10, w10 = real.mean(), (real > 0).sum()
                    wr10 = 100*w10/len(sub)
                else:
                    e15 = real.mean()
            print(f"{label:45s}  {d:5s}  {len(sub):>5d}  {mfe.mean():>5.1f}  "
                  f"{mae.mean():>5.1f}  {e10:>+8.2f}  {e15:>+8.2f}  {wr10:>4.0f}%")
        print()


if __name__ == "__main__":
    main()
