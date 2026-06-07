"""
Step 2 — Detect and label swing pivots on M5.

Algorithm (mirrors the user's arrow placement in the screenshot):
  Pip-threshold ZigZag — direction flips when price retraces THRESH pips from the
  current extreme. The bar that held the extreme = the pivot.

Each pivot gets two timestamps:
  - pivot_time      : the bar that was the actual extreme high/low (what an arrow points at)
  - confirm_time    : the bar where the retracement crossed the threshold
                      (the EARLIEST a live system could act without lookahead)

Labels (HH/HL/LH/LL) computed relative to the previous SAME-TYPE swing:
  swing HIGH > prev swing HIGH → HH (Higher High)
  swing HIGH < prev swing HIGH → LH (Lower High)
  swing LOW  > prev swing LOW  → HL (Higher Low)
  swing LOW  < prev swing LOW  → LL (Lower Low)

We sweep multiple thresholds so we can pick the one giving the right pivot
frequency to match the user's chart density.

Reads:  /home/cmake/Vector/research/m5_with_indicators.csv.gz
Writes: /home/cmake/Vector/research/pivots_thresh<N>.csv  (one per threshold)
"""

import pandas as pd
import numpy as np

SRC = "/home/cmake/Vector/research/m5_with_indicators.csv.gz"
OUT_DIR = "/home/cmake/Vector/research"
PIP = 0.0001

# Thresholds to sweep, in pips
THRESHOLDS_PIPS = [5, 8, 10, 12, 15, 20, 25, 30]


def detect_pivots(df: pd.DataFrame, thresh_pips: float) -> pd.DataFrame:
    """
    Walk forward; track current direction (up/down) and the extreme in that direction.
    Flip when price retraces THRESH from the extreme. Record (pivot_time, confirm_time, price).
    """
    thresh = thresh_pips * PIP

    h = df["high"].values
    l = df["low"].values
    t = df.index.values   # numpy datetime64

    # State: direction True=up (we're tracking the running HIGH), False=down (tracking LOW)
    # Initialise by looking at first 2 bars
    n = len(df)
    if n < 3:
        return pd.DataFrame()

    direction_up = h[1] >= h[0]
    ext = h[1] if direction_up else l[1]
    ext_i = 1

    out = []  # (pivot_time, confirm_time, price, is_high)

    for i in range(2, n):
        if direction_up:
            if h[i] > ext:
                ext, ext_i = h[i], i
            elif l[i] <= ext - thresh:
                # confirmed swing HIGH at index ext_i
                out.append((t[ext_i], t[i], ext, True))
                direction_up = False
                ext, ext_i = l[i], i
        else:
            if l[i] < ext:
                ext, ext_i = l[i], i
            elif h[i] >= ext + thresh:
                # confirmed swing LOW at index ext_i
                out.append((t[ext_i], t[i], ext, False))
                direction_up = True
                ext, ext_i = h[i], i

    piv = pd.DataFrame(out, columns=["pivot_time", "confirm_time", "price", "is_high"])
    if piv.empty:
        return piv

    # Label HH/HL/LH/LL
    prev_high = None
    prev_low  = None
    labels = []
    for _, row in piv.iterrows():
        if row["is_high"]:
            if prev_high is None:
                labels.append("H")          # first swing high — unknown direction
            else:
                labels.append("HH" if row["price"] > prev_high else "LH")
            prev_high = row["price"]
        else:
            if prev_low is None:
                labels.append("L")
            else:
                labels.append("HL" if row["price"] > prev_low else "LL")
            prev_low = row["price"]
    piv["label"] = labels

    # Bars between pivot and confirmation, and inter-pivot spacing
    piv["confirm_lag_bars"] = ((piv["confirm_time"] - piv["pivot_time"])
                               .dt.total_seconds() / 300).astype(int)
    piv["bars_since_prev"]  = ((piv["pivot_time"] - piv["pivot_time"].shift())
                               .dt.total_seconds() / 300).fillna(0).astype(int)

    return piv


def main():
    print("loading dataset...")
    df = pd.read_csv(SRC, index_col=0, parse_dates=True)
    print(f"  {len(df):,} M5 bars")

    print("\nSweeping thresholds to find pivot frequency:")
    print(f"{'thresh':>8s}  {'pivots':>7s}  {'pivots/day':>11s}  {'HH':>5s} {'HL':>5s} {'LH':>5s} {'LL':>5s}  {'avg_lag':>8s}")
    days = (df.index[-1] - df.index[0]).total_seconds() / 86400

    summaries = []
    for th in THRESHOLDS_PIPS:
        piv = detect_pivots(df, th)
        cnts = piv["label"].value_counts().to_dict()
        per_day = len(piv) / days
        avg_lag = piv["confirm_lag_bars"].mean() if not piv.empty else 0
        print(f"{th:>6d}pip  {len(piv):>7d}  {per_day:>11.2f}  "
              f"{cnts.get('HH',0):>5d} {cnts.get('HL',0):>5d} "
              f"{cnts.get('LH',0):>5d} {cnts.get('LL',0):>5d}  "
              f"{avg_lag:>8.1f}")
        summaries.append((th, piv))

        # Save each
        out = f"{OUT_DIR}/pivots_thresh{th}.csv"
        piv.to_csv(out, index=False)

    print(f"\nSaved {len(summaries)} pivot files to {OUT_DIR}/pivots_thresh*.csv")


if __name__ == "__main__":
    main()
