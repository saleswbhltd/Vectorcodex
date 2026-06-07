"""
Step 22 — M1 EARLY ENTRY on 2026 data.

Detect pivots on M5 at 20-pip threshold (the best 2026 operating point).
Apply G1+G3+G6 filter using M5 features.
For each filtered pivot, use M1 data to find the EARLIEST bar where price
retraced N pips from the pivot extreme — that's the early-entry bar.
Compute realistic MFE/MAE from THAT entry.

This tests whether M1 granularity actually delivers the predicted lift from
simulation step 19, on the new 2026 data.
"""

import pandas as pd
import numpy as np

M5_DATA = "/home/cmake/Vector/research/m5_2026_deep.csv.gz"
M1_DATA = "/home/cmake/Vector/research/m1_2026_deep.csv.gz"
PIP = 0.0001
M5_THRESH = 20
LOOKAHEAD_MIN = 60   # 60 min of forward window
EARLY_RETRACE_OPTIONS = [3, 5, 8, 10, 15, 20]  # pips


def detect_pivots(df, thresh_pips):
    thresh = thresh_pips * PIP
    h = df["high"].values; l = df["low"].values; t = df.index.values
    n = len(df)
    direction_up = h[1] >= h[0]
    ext = h[1] if direction_up else l[1]; ext_i = 1
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
    print("loading M5...")
    m5 = pd.read_csv(M5_DATA, index_col=0, parse_dates=True)
    print(f"  {len(m5):,} M5 bars")
    print("loading M1...")
    m1 = pd.read_csv(M1_DATA, index_col=0, parse_dates=True)
    print(f"  {len(m1):,} M1 bars  ({m1.index[0]} → {m1.index[-1]})")

    piv = detect_pivots(m5, M5_THRESH)
    piv["confirm_lag"] = ((piv["confirm_time"] - piv["pivot_time"])
                          .dt.total_seconds() / 300).astype(int)
    print(f"\nM5 pivots @ {M5_THRESH} pip: {len(piv)}")

    # Apply G1+G3+G6 filter using M5 indicators at pivot bar
    atr14 = m5["atr14_pips"].values
    d2low = m5["dist_to_today_low_pips"].values
    M5H = m5["high"].values; M5L = m5["low"].values; M5C = m5["close"].values

    # Filter
    filt = []
    for _, p in piv.iterrows():
        pi = int(p["pi"])
        if not (6 <= atr14[pi] <= 11): continue
        if d2low[pi] > 80: continue
        if p["confirm_lag"] > 8: continue
        # Must have M1 coverage at pivot time
        if p["pivot_time"] < m1.index[0]: continue
        filt.append(p)
    piv_filt = pd.DataFrame(filt)
    print(f"After G1+G3+G6 filter + M1 coverage: {len(piv_filt)}")
    if len(piv_filt) == 0:
        print("No filtered pivots in M1 coverage window")
        return

    # For each filtered pivot, find M1 entry at various retracement levels
    M1H = m1["high"].values; M1L = m1["low"].values; M1C = m1["close"].values
    m1_idx = pd.Series(range(len(m1)), index=m1.index)
    # 60 min = 60 M1 bars
    LOOK_M1 = 60

    print(f"\n{'thresh':>7s}  {'side':>4s}  {'n':>4s}  {'avg_lag':>7s}  "
          f"{'MFE':>5s}  {'MAE':>5s}  {'SL10':>7s}  {'SL15':>7s}  {'WR10':>4s}")
    for retrace in EARLY_RETRACE_OPTIONS:
        for d_label, is_high_flag in [("SELL", True), ("BUY", False)]:
            rows = []
            for _, p in piv_filt.iterrows():
                if bool(p["is_high"]) != is_high_flag: continue
                pivot_px = p["price"]
                trigger = pivot_px - retrace*PIP if is_high_flag else pivot_px + retrace*PIP

                # Find first M1 bar at/after pivot_time where M1 crosses trigger
                # Use searchsorted for speed
                # Limit search to 60 min (60 M1 bars) after pivot
                if p["pivot_time"] not in m1.index:
                    # find nearest M1 bar at/after pivot_time
                    idx_arr = m1.index.searchsorted(p["pivot_time"])
                    if idx_arr >= len(m1): continue
                    start_i = idx_arr
                else:
                    start_i = int(m1_idx[p["pivot_time"]])

                trig_i = None
                for k in range(LOOK_M1):
                    j = start_i + k
                    if j >= len(m1): break
                    if is_high_flag and M1L[j] <= trigger:
                        trig_i = j; break
                    if (not is_high_flag) and M1H[j] >= trigger:
                        trig_i = j; break
                if trig_i is None: continue
                # Entry at this M1 bar's close
                entry = M1C[trig_i]
                # Now look forward LOOK_M1 bars (= 60 min) for MFE/MAE
                end = min(trig_i + LOOK_M1, len(m1))
                mfe = 0.0; mae = 0.0
                for k in range(trig_i+1, end):
                    if is_high_flag:
                        fav = (entry - M1L[k])/PIP; adv = (M1H[k] - entry)/PIP
                    else:
                        fav = (M1H[k] - entry)/PIP; adv = (entry - M1L[k])/PIP
                    if fav > mfe: mfe = fav
                    if adv > mae: mae = adv
                rows.append({"entry_lag_m1_bars": trig_i - start_i,
                             "mfe": mfe, "mae": mae})

            sub = pd.DataFrame(rows)
            if len(sub) == 0: continue
            mfe = sub["mfe"]; mae = sub["mae"]
            r10 = np.where(mae >= 10, -10, np.maximum(mfe-10, 0))
            r15 = np.where(mae >= 15, -15, np.maximum(mfe-15, 0))
            wr10 = 100*(r10 > 0).sum()/len(sub)
            print(f"{retrace:>4d}pip  {d_label:>4s}  {len(sub):>4d}  "
                  f"{sub['entry_lag_m1_bars'].mean():>6.1f}m  "
                  f"{mfe.mean():>5.1f}  {mae.mean():>5.1f}  "
                  f"{r10.mean():>+6.2f}  {r15.mean():>+6.2f}  {wr10:>3.0f}%")
        print()


if __name__ == "__main__":
    main()
