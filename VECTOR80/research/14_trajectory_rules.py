"""
Step 14 — Test ENTRY GATES derived from the trajectory analysis.

Trajectory insight: ELITE pivots happen in MODERATE vol (ATR 6–11, BB width 25–55)
with structurally mature but not extended day positioning (within 80 pips of
today's low for both SELL and BUY), preceded by a small confirming streak.

Rules tested:
  G1: atr14_pips in [6, 11]                     (moderate vol)
  G2: bb_width_pips in [25, 55]                 (moderate bands)
  G3: dist_to_today_low_pips <= 80              (not chasing extension)
  G4: range_pips_t-5 < 14                       (no pre-pivot vol blow-out)
  G5: SELL: consec_up_t-5 >= 1; BUY: consec_dn_t-5 >= 1   (1+ confirming bars)
  G6: confirm_lag <= 8                          (decisive retracement)

Counts ELITE/STRONG/MIXED/WAFFLE/FAILED for trades passing each gate combination.
Uses the same temporal panel + MFE/MAE outcomes from steps 11-12.
Walk-forward: H1 2025 vs H2 2025.
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


def apply_gates(df, gates):
    """gates = list of (label, boolean Series). Returns filtered df + counts table."""
    mask = pd.Series(True, index=df.index)
    for lbl, m in gates:
        mask &= m
    return df[mask], mask


def summarize(label, sub, total):
    if len(sub) == 0:
        print(f"  {label}: 0 trades"); return
    t = sub["tier"].value_counts()
    elite = t.get("ELITE", 0); strong = t.get("STRONG", 0)
    waffle = t.get("WAFFLE", 0); failed = t.get("FAILED", 0)
    mixed = t.get("MIXED", 0)
    good = elite + strong
    print(f"  {label}: n={len(sub):4d}  cov={100*len(sub)/total:5.1f}%   "
          f"ELITE={elite:3d} ({100*elite/len(sub):.1f}%)  "
          f"STRONG={strong:3d}  MIXED={mixed:3d}  WAFFLE={waffle:3d}  "
          f"FAILED={failed:3d} ({100*failed/len(sub):.1f}%)  "
          f"good={good}/{len(sub)}={100*good/len(sub):.1f}%   "
          f"avg MFE_60m={sub['mfe_60m'].mean():.1f}  "
          f"avg MAE_60m={sub['mae_60m'].mean():.1f}")


def main():
    panel = pd.read_csv(SRC_PANEL, parse_dates=["pivot_time","confirm_time"])
    mm    = pd.read_csv(SRC_MFEMAE, parse_dates=["pivot_time"])
    df = panel.merge(mm, on=["pivot_time","direction"], how="inner")
    df["tier"] = df.apply(assign_tier, axis=1)
    print(f"loaded {len(df):,} pivots")
    print(f"baseline tier mix:")
    print(df.groupby(["direction","tier"]).size().unstack(fill_value=0))

    # Split train/test
    train = df[df["pivot_time"] < SPLIT].copy()
    test  = df[df["pivot_time"] >= SPLIT].copy()
    print(f"\ntrain={len(train)}  test={len(test)}")

    # Helper functions — pick the column for the right offset
    def col(feat, off):
        return f"{feat}_t{off:+d}"

    # ── Define gate Series for any DataFrame ──
    def gates_for(d, direction):
        sub = d[d["direction"] == direction].copy()
        atr = sub[col("atr14_pips", 0)]
        bbw = sub[col("bb_width_pips", 0)]
        d2low = sub[col("dist_to_today_low_pips", 0)]
        rng5  = sub[col("range_pips", -1)]
        if direction == "SELL":
            confbars = sub[col("consec_up", -1)]
        else:
            confbars = sub[col("consec_dn", -1)]
        return sub, {
            "G1 atr14∈[6,11]":       atr.between(6, 11),
            "G2 bbw∈[25,55]":        bbw.between(25, 55),
            "G3 d2low≤80":           d2low <= 80,
            "G4 range_t-5<14":       rng5 < 14,
            "G5 confbars≥1":         confbars >= 1,
            "G6 confirm_lag≤8":      sub["confirm_lag"] <= 8,
        }

    # ── Test each gate ALONE then in combo ──
    for tset_label, tset in [("TRAIN H1", train), ("TEST H2", test)]:
        print(f"\n{'='*78}\n{tset_label}\n{'='*78}")
        for direction in ("SELL", "BUY"):
            print(f"\n── {direction} ──")
            sub, gs = gates_for(tset, direction)
            print(f"  baseline (all pivots):")
            summarize("baseline ", sub, len(sub))
            print(f"  individual gates:")
            for lbl, m in gs.items():
                summarize(f"  {lbl:20s}", sub[m], len(sub))
            # Combined
            print(f"  combined gates:")
            combos = [
                ("G1+G2+G3 only",   ["G1 atr14∈[6,11]", "G2 bbw∈[25,55]", "G3 d2low≤80"]),
                ("G1+G3+G6",        ["G1 atr14∈[6,11]", "G3 d2low≤80", "G6 confirm_lag≤8"]),
                ("G1+G2+G3+G4+G5",  ["G1 atr14∈[6,11]", "G2 bbw∈[25,55]", "G3 d2low≤80",
                                     "G4 range_t-5<14", "G5 confbars≥1"]),
                ("ALL 6 gates",     list(gs.keys())),
            ]
            for name, keys in combos:
                mask = pd.Series(True, index=sub.index)
                for k in keys: mask &= gs[k]
                summarize(name, sub[mask], len(sub))


if __name__ == "__main__":
    main()
