"""
Step 16 — Recompute MFE/MAE from REALISTIC entry: the CONFIRM bar close.

Previous step measured MFE/MAE from the pivot's actual high/low (impossible
perfect entry). The realistic moment we can act is the confirm bar — by which
point price has already retraced THRESH=15 pips.

This script recomputes MFE/MAE from confirm-bar close prices, then re-applies
the G1+G3+G6 trajectory rule and reports the HONEST per-trade outcome.
"""

import pandas as pd
import numpy as np

DATA   = "/home/cmake/Vector/research/m5_deep.csv.gz"
PIVOTS = "/home/cmake/Vector/research/pivots_thresh15.csv"
PANEL  = "/home/cmake/Vector/research/pivot_panel.csv"
SPLIT  = "2025-07-01"
PIP    = 0.0001
SAMPLE_BARS = [1, 3, 6, 12, 24, 48]   # 5..240 min


def main():
    df  = pd.read_csv(DATA, index_col=0, parse_dates=True)
    piv = pd.read_csv(PIVOTS, parse_dates=["pivot_time","confirm_time"])
    piv = piv[piv["label"].isin(["HH","HL","LH","LL"])].copy()
    panel = pd.read_csv(PANEL, parse_dates=["pivot_time","confirm_time"])

    bar_idx = pd.Series(range(len(df)), index=df.index)
    H = df["high"].values; L = df["low"].values; C = df["close"].values

    rows = []
    for _, p in piv.iterrows():
        if p["confirm_time"] not in bar_idx.index: continue
        ci = int(bar_idx.loc[p["confirm_time"]])
        if ci + max(SAMPLE_BARS) >= len(df): continue

        is_high = bool(p["is_high"])
        entry = C[ci]    # we enter at confirm bar close
        direction = "SELL" if is_high else "BUY"

        run_mfe = 0.0
        run_mae = 0.0
        out = {"pivot_time": p["pivot_time"], "confirm_time": p["confirm_time"],
               "direction": direction, "label": p["label"],
               "entry_px": entry, "confirm_lag": p["confirm_lag_bars"]}
        for k in range(1, max(SAMPLE_BARS) + 1):
            j = ci + k
            hh = H[j]; ll = L[j]
            if is_high:                 # SELL
                fav = (entry - ll) / PIP
                adv = (hh - entry) / PIP
            else:                       # BUY
                fav = (hh - entry) / PIP
                adv = (entry - ll) / PIP
            if fav > run_mfe: run_mfe = fav
            if adv > run_mae: run_mae = adv
            if k in SAMPLE_BARS:
                m = k * 5
                out[f"mfe_{m}m"] = run_mfe
                out[f"mae_{m}m"] = run_mae
        rows.append(out)

    out = pd.DataFrame(rows)
    # Merge with panel to recover the gate features
    out = out.merge(panel[["pivot_time","direction","atr14_pips_t+0",
                            "dist_to_today_low_pips_t+0"]],
                    on=["pivot_time","direction"], how="left")

    # Apply gates
    g1 = out["atr14_pips_t+0"].between(6, 11)
    g3 = out["dist_to_today_low_pips_t+0"] <= 80
    g6 = out["confirm_lag"] <= 8
    out["passes"] = g1 & g3 & g6

    print(f"\n=== REALISTIC entry MFE/MAE (from confirm bar) ===")
    print(f"total pivots: {len(out)}, filter pass: {out['passes'].sum()}")

    for label, sub in [("ALL pivots", out),
                       ("filter-pass G1+G3+G6", out[out["passes"]])]:
        print(f"\n── {label} ──")
        for d in ("SELL", "BUY"):
            s = sub[sub["direction"]==d]
            tr = s[s["pivot_time"] < SPLIT]
            te = s[s["pivot_time"] >= SPLIT]
            print(f"  {d}: train n={len(tr)}  test n={len(te)}")
            for h in [30, 60, 120, 240]:
                mfe = te[f"mfe_{h}m"]; mae = te[f"mae_{h}m"]
                if len(mfe) == 0: continue
                net = mfe - mae
                # Trail strategy: exit when mae > trail_pips for ALL prior bars... we don't
                # have that without bar-by-bar replay. Simple proxy: assume entry stop at
                # SL pips, lose SL pips if mae >= SL, otherwise win mfe pips (max possible)
                for sl in [10, 15, 20]:
                    # Realistic worst-case: if MAE >= SL first → lose SL
                    # We don't have time-order of MAE vs MFE — use heuristic:
                    # if MAE >= SL: assume stop hit → -SL
                    # else: realize the MFE - SL (trail back SL pips from peak)
                    real = np.where(mae >= sl, -sl, np.maximum(mfe - sl, 0))
                    wins = (real > 0).sum()
                    print(f"    @ {h:3d}min  SL={sl:2d}:  avg net={real.mean():+5.1f}  "
                          f"wins={wins}/{len(mfe):3d} ({100*wins/len(mfe):.0f}%)  "
                          f"total={real.sum():+5.0f}  "
                          f"MFE avg={mfe.mean():.1f} median={mfe.median():.1f}  "
                          f"MAE avg={mae.mean():.1f} median={mae.median():.1f}")
            # Show MAE distribution quantiles
            print(f"    MAE distribution @ 60min: "
                  f"p25={te['mae_60m'].quantile(0.25):.1f}  "
                  f"p50={te['mae_60m'].median():.1f}  "
                  f"p75={te['mae_60m'].quantile(0.75):.1f}  "
                  f"p90={te['mae_60m'].quantile(0.90):.1f}")


if __name__ == "__main__":
    main()
