"""
Step 15 — Final validation of the trajectory-derived rule (G1+G3+G6).

Hard-locks the train-set numerical thresholds and applies them to the test
set blind. Then reports:
  - trade frequency and timing (when do entries fire?)
  - MFE/MAE distributions at 30/60/120 min (full picture, not just averages)
  - what happens if we use a trailing stop with TP=open-ended
"""

import pandas as pd
import numpy as np

SRC_PANEL = "/home/cmake/Vector/research/pivot_panel.csv"
SRC_MFEMAE = "/home/cmake/Vector/research/mfe_mae.csv"
SPLIT = "2025-07-01"


def assign_tier(r):
    if r["mfe_60m"] >= 25 and r["mae_60m"] <= 5: return "ELITE"
    if r["mfe_30m"] >= 20 and r["mae_30m"] <= 5: return "STRONG"
    if r["mae_30m"] >= 15 and r["mae_30m"] > r["mfe_30m"]: return "FAILED"
    if r["mfe_60m"] < 10 and r["mae_60m"] < 10: return "WAFFLE"
    return "MIXED"


def main():
    panel = pd.read_csv(SRC_PANEL, parse_dates=["pivot_time","confirm_time"])
    mm    = pd.read_csv(SRC_MFEMAE, parse_dates=["pivot_time"])
    df = panel.merge(mm, on=["pivot_time","direction"], how="inner")
    df["tier"] = df.apply(assign_tier, axis=1)

    # Hard-locked thresholds from train-set analysis
    g1 = df["atr14_pips_t+0"].between(6, 11)
    g3 = df["dist_to_today_low_pips_t+0"] <= 80
    g6 = df["confirm_lag"] <= 8
    df["passes_filter"] = g1 & g3 & g6

    test = df[df["pivot_time"] >= SPLIT].copy()
    train = df[df["pivot_time"] < SPLIT].copy()
    print(f"train n={len(train)}  test n={len(test)}")

    for label, T in [("TRAIN", train), ("TEST", test)]:
        print(f"\n{'='*78}\n{label} SET — overall filter pass rate\n{'='*78}")
        filt = T[T["passes_filter"]]
        print(f"baseline n={len(T)}  filtered n={len(filt)}  ({100*len(filt)/len(T):.1f}% pass)")

        for direction in ("SELL", "BUY"):
            sub = filt[filt["direction"] == direction]
            base = T[T["direction"] == direction]
            if sub.empty: continue
            t = sub["tier"].value_counts().to_dict()
            elite_pct = 100 * t.get("ELITE", 0) / len(sub)
            good_pct  = 100 * (t.get("ELITE", 0) + t.get("STRONG", 0)) / len(sub)
            print(f"\n  {direction}: n={len(sub)}  ELITE={elite_pct:.1f}%  good={good_pct:.1f}%")
            for h in [30, 60, 120, 240]:
                mfe = sub[f"mfe_{h}m"]
                mae = sub[f"mae_{h}m"]
                print(f"    @ {h:3d}min: MFE avg={mfe.mean():.1f}  median={mfe.median():.1f}  "
                      f"p25={mfe.quantile(0.25):.1f}  p75={mfe.quantile(0.75):.1f}  "
                      f"||  MAE avg={mae.mean():.1f}  median={mae.median():.1f}  "
                      f"p75={mae.quantile(0.75):.1f}")

            # Trailing strategy simulation:
            # Enter at PIVOT BAR (impossible perfect entry — note caveat)
            # Trail at 8 pips behind max favorable. Exit when price retraces 8 pips from max.
            # Approximate by: realized = MFE - 8 if MFE > 8, else -MAE (rough heuristic)
            # Better simple model: realized_60m = max(0, MFE_60m - 5) — give back 5 pips on the trail
            for tp_floor, sl in [("trail", 8), ("trail", 12), ("trail", 16)]:
                # If MFE > sl, win ≈ MFE - sl (trail captures most of the move)
                # Else: lose min(MAE, sl) ≈ stop at sl pips back
                realized = np.where(sub["mfe_60m"] > sl,
                                    sub["mfe_60m"] - sl,
                                    -np.minimum(sub["mae_60m"], sl))
                avg = realized.mean()
                wins = (realized > 0).sum()
                print(f"    trail-{sl}pip @ 60m: avg P&L = {avg:+.1f} pips  "
                      f"wins {wins}/{len(sub)} ({100*wins/len(sub):.0f}%)  "
                      f"total {realized.sum():+.0f} pips on {len(sub)} trades")

    # Show timing distribution
    print(f"\n{'='*78}\nTEST SET — filtered trades by hour-of-day")
    print('='*78)
    tt = test[test["passes_filter"]].copy()
    tt["hour"] = pd.to_datetime(tt["pivot_time"]).dt.hour
    print(tt.groupby(["direction", "hour"]).size().unstack(fill_value=0))

    # By month
    print(f"\nTEST SET — filtered trades by month")
    tt["month"] = pd.to_datetime(tt["pivot_time"]).dt.to_period("M").astype(str)
    print(tt.groupby(["direction", "month"]).size().unstack(fill_value=0))


if __name__ == "__main__":
    main()
