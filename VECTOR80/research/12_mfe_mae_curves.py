"""
Step 12 — Time-resolved MFE/MAE curves per pivot.

For each pivot, walking forward from the PIVOT BAR (not confirm bar — we want
the dynamics from the moment the arrow appears), compute:

  MFE_at_t — max favourable excursion (pips) by time t
  MAE_at_t — max adverse  excursion (pips) by time t

Directionality:
  SELL pivot (high formed)  →  favourable = price DOWN, adverse = UP
  BUY  pivot (low formed)   →  favourable = price UP,   adverse = DOWN

Sampled at t = 1, 2, 3, 6, 12, 24, 48 M5 bars  (5, 10, 15, 30, 60, 120, 240 min).

Reference price = pivot's actual high (SELL) or low (BUY) — i.e. the price the
arrow points at. This is the "perfect entry" scenario.

Output:
  mfe_mae.csv  one row per pivot with cols mfe_5m, mae_5m, mfe_10m, mae_10m, ...
  Plus pivot_time, direction, label.
"""

import pandas as pd
import numpy as np

SRC_INDICATORS = "/home/cmake/Vector/research/m5_deep.csv.gz"
SRC_PIVOTS     = "/home/cmake/Vector/research/pivots_thresh15.csv"
OUT            = "/home/cmake/Vector/research/mfe_mae.csv"

PIP = 0.0001
SAMPLE_BARS = [1, 2, 3, 6, 12, 24, 48]    # 5, 10, 15, 30, 60, 120, 240 min


def main():
    df  = pd.read_csv(SRC_INDICATORS, index_col=0, parse_dates=True)
    piv = pd.read_csv(SRC_PIVOTS, parse_dates=["pivot_time", "confirm_time"])
    piv = piv[piv["label"].isin(["HH","HL","LH","LL"])].copy()
    print(f"loaded {len(df):,} bars, {len(piv):,} pivots")

    bar_idx = pd.Series(range(len(df)), index=df.index)
    H = df["high"].values
    L = df["low"].values

    rows = []
    for _, p in piv.iterrows():
        if p["pivot_time"] not in bar_idx.index: continue
        i = int(bar_idx.loc[p["pivot_time"]])
        # Reference = the actual pivot price (high for SELL, low for BUY)
        ref = p["price"]
        is_high = bool(p["is_high"])
        direction = "SELL" if is_high else "BUY"

        last_bar = i + max(SAMPLE_BARS)
        if last_bar >= len(df): continue

        row = {
            "pivot_time": p["pivot_time"],
            "label":      p["label"],
            "direction":  direction,
            "pivot_price": ref,
        }
        # Track running MFE/MAE
        run_mfe = 0.0
        run_mae = 0.0
        next_sample_idx = 0
        for k in range(1, max(SAMPLE_BARS) + 1):
            j = i + k
            hh = H[j]; ll = L[j]
            if is_high:                 # SELL → fav = down
                fav_excur = (ref - ll) / PIP
                adv_excur = (hh - ref) / PIP
            else:                       # BUY → fav = up
                fav_excur = (hh - ref) / PIP
                adv_excur = (ref - ll) / PIP
            if fav_excur > run_mfe: run_mfe = fav_excur
            if adv_excur > run_mae: run_mae = adv_excur
            if k == SAMPLE_BARS[next_sample_idx]:
                minutes = k * 5
                row[f"mfe_{minutes}m"] = run_mfe
                row[f"mae_{minutes}m"] = run_mae
                row[f"net_{minutes}m"] = run_mfe - run_mae   # rough notion of edge captured
                next_sample_idx += 1
                if next_sample_idx >= len(SAMPLE_BARS): break

        rows.append(row)

    out = pd.DataFrame(rows)
    out.to_csv(OUT, index=False, float_format="%.2f")
    print(f"saved {len(out):,} rows → {OUT}")

    # ── Quick summary by direction at key horizons ──
    print("\n── Avg MFE / MAE / net by direction ──")
    print(f"{'horizon':>9s}  {'side':>5s}  {'n':>4s}  {'MFE':>6s}  {'MAE':>6s}  {'net':>6s}")
    for h in SAMPLE_BARS:
        m = h * 5
        for d in ("SELL", "BUY"):
            sub = out[out["direction"] == d]
            print(f"{m:>6d}min  {d:>5s}  {len(sub):>4d}  "
                  f"{sub[f'mfe_{m}m'].mean():>6.1f}  "
                  f"{sub[f'mae_{m}m'].mean():>6.1f}  "
                  f"{sub[f'net_{m}m'].mean():>+6.1f}")


if __name__ == "__main__":
    main()
