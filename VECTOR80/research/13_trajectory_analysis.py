"""
Step 13 — Trajectory / signature analysis.

Joins:
  pivot_panel.csv   — indicator values at -30/-15/-5/0/+5/+15/+30 min per pivot
  mfe_mae.csv       — time-resolved MFE/MAE per pivot

Defines pivot OUTCOME tiers using MFE/MAE — NOT TP/SL:
  ELITE      — MFE_60m ≥ 25 pips AND MAE_60m ≤ 5 pips
                (strong clean follow-through, virtually no drawdown)
  STRONG     — MFE_30m ≥ 20 pips AND MAE_30m ≤ 5 pips
                (fast clean move)
  WAFFLE     — MFE_60m < 10 AND MAE_60m < 10
                (no follow-through, market went flat)
  FAILED     — MAE_30m ≥ 15 pips AND MAE_30m > MFE_30m
                (went the wrong way fast)

For each indicator, computes the MEAN TRAJECTORY across the 7 time offsets
for ELITE pivots, FAILED pivots, and ALL pivots. The bigger the spread
between ELITE and FAILED at a given offset = the more predictive that feature
is at that moment in time.

Output:
  trajectory_table.csv  — feature × offset × tier × mean value
  signature_lift.csv     — features ranked by max ELITE-vs-FAILED gap
  TRAJECTORY_REPORT.md   — human-readable summary
"""

import pandas as pd
import numpy as np

SRC_PANEL = "/home/cmake/Vector/research/pivot_panel.csv"
SRC_MFEMAE = "/home/cmake/Vector/research/mfe_mae.csv"
OUT_TRAJ  = "/home/cmake/Vector/research/trajectory_table.csv"
OUT_LIFT  = "/home/cmake/Vector/research/signature_lift.csv"
OUT_MD    = "/home/cmake/Vector/research/TRAJECTORY_REPORT.md"

OFFSETS = [-6, -3, -1, 0, 1, 3, 6]                # bars
OFFSETS_MIN = {off: off*5 for off in OFFSETS}

TRACKED_FEATURES = [
    "atr5", "atr14_pips",
    "rsi14", "stoch_k", "stoch_d",
    "macd", "macd_hist",
    "bb_pctB", "bb_width_pips", "bb_squeeze",
    "adx14", "plus_di", "minus_di",
    "velocity_3", "accel",
    "body_pips", "range_pips", "body_to_range",
    "upper_wick_ratio", "lower_wick_ratio",
    "vol_z20", "range_z20",
    "dist_ema20_atr",
    "williams_r14",
    "consec_up", "consec_dn",
    "dist_to_5bar_high_pips", "dist_to_5bar_low_pips",
    "dist_to_20bar_high_pips", "dist_to_20bar_low_pips",
    "dist_to_today_high_pips", "dist_to_today_low_pips",
]


def assign_tier(r):
    if r["mfe_60m"] >= 25 and r["mae_60m"] <= 5: return "ELITE"
    if r["mfe_30m"] >= 20 and r["mae_30m"] <= 5: return "STRONG"
    if r["mae_30m"] >= 15 and r["mae_30m"] > r["mfe_30m"]: return "FAILED"
    if r["mfe_60m"] < 10 and r["mae_60m"] < 10: return "WAFFLE"
    return "MIXED"


def main():
    panel = pd.read_csv(SRC_PANEL, parse_dates=["pivot_time","confirm_time"])
    mm    = pd.read_csv(SRC_MFEMAE, parse_dates=["pivot_time"])

    # Join on pivot_time + direction (label kept as tie-breaker)
    df = panel.merge(mm, on=["pivot_time", "direction"], how="inner",
                     suffixes=("", "_mm"))
    print(f"joined {len(df):,} pivots")
    if "label_mm" in df.columns: df = df.drop(columns=["label_mm"])

    df["tier"] = df.apply(assign_tier, axis=1)

    # Tier distribution
    print("\nTier distribution by direction:")
    print(df.groupby(["direction", "tier"]).size().unstack(fill_value=0))

    # Build trajectory table: rows = feature×offset×tier
    print("\nBuilding trajectory table...")
    traj = []
    for feat in TRACKED_FEATURES:
        for off in OFFSETS:
            col = f"{feat}_t{off:+d}"
            if col not in df.columns: continue
            for direction in ("SELL", "BUY"):
                sub_dir = df[df["direction"] == direction]
                for tier in ("ELITE", "STRONG", "WAFFLE", "FAILED", "ALL"):
                    if tier == "ALL":
                        sub = sub_dir
                    else:
                        sub = sub_dir[sub_dir["tier"] == tier]
                    if len(sub) < 5: continue
                    vals = sub[col].dropna()
                    if len(vals) < 5: continue
                    traj.append({
                        "feature": feat, "offset_bars": off,
                        "offset_min": OFFSETS_MIN[off],
                        "direction": direction, "tier": tier,
                        "n": len(vals), "mean": vals.mean(),
                        "median": vals.median(), "std": vals.std(),
                    })
    traj = pd.DataFrame(traj)
    traj.to_csv(OUT_TRAJ, index=False, float_format="%.4f")
    print(f"saved → {OUT_TRAJ}")

    # ── Signature lift: where do ELITE vs FAILED differ most? ──
    print("\nComputing ELITE-vs-FAILED signature lift...")
    lift = []
    for feat in TRACKED_FEATURES:
        for off in OFFSETS:
            for direction in ("SELL", "BUY"):
                ef = traj[(traj["feature"] == feat) &
                          (traj["offset_bars"] == off) &
                          (traj["direction"] == direction)]
                eli = ef[ef["tier"] == "ELITE"]
                fai = ef[ef["tier"] == "FAILED"]
                if eli.empty or fai.empty: continue
                e_mean = eli.iloc[0]["mean"]
                f_mean = fai.iloc[0]["mean"]
                e_std  = eli.iloc[0]["std"]
                f_std  = fai.iloc[0]["std"]
                pooled_std = np.sqrt((e_std**2 + f_std**2) / 2)
                cohens_d = (e_mean - f_mean) / pooled_std if pooled_std > 0 else 0
                lift.append({
                    "feature": feat, "offset_bars": off,
                    "offset_min": OFFSETS_MIN[off],
                    "direction": direction,
                    "elite_mean": e_mean, "failed_mean": f_mean,
                    "abs_gap": abs(e_mean - f_mean),
                    "cohens_d": cohens_d,
                })
    lift = pd.DataFrame(lift).sort_values("cohens_d", key=lambda s: s.abs(), ascending=False)
    lift.to_csv(OUT_LIFT, index=False, float_format="%.4f")
    print(f"saved → {OUT_LIFT}")

    # Print top signature lifts
    print("\n=== TOP 20 ELITE-vs-FAILED signature gaps (Cohen's d) ===")
    print(lift.head(20)[["feature","offset_min","direction","elite_mean","failed_mean","cohens_d"]]
          .to_string(index=False, float_format="%.2f"))

    # ── Build human report ──
    lines = []
    lines.append("# Pivot Trajectory Analysis — ELITE vs FAILED Signature")
    lines.append("")
    lines.append("**Method:** for each indicator, mean value across pivots at offsets "
                 "-30/-15/-5/0/+5/+15/+30 min around the pivot bar. "
                 "Compared between ELITE outcomes (MFE_60m≥25 AND MAE_60m≤5) "
                 "and FAILED outcomes (MAE_30m≥15 AND MAE>MFE).")
    lines.append("")
    lines.append("## Tier counts")
    counts = df.groupby(["direction","tier"]).size().unstack(fill_value=0)
    lines.append("```")
    lines.append(counts.to_string())
    lines.append("```")
    lines.append("")

    # Pull the strongest 12 signatures per direction
    for direction in ("SELL", "BUY"):
        sub = lift[lift["direction"] == direction].head(15)
        lines.append(f"## TOP 15 signature features — {direction} pivots")
        lines.append("")
        lines.append("| Feature | Offset | ELITE mean | FAILED mean | gap | Cohen's d |")
        lines.append("|---|---|---|---|---|---|")
        for _, r in sub.iterrows():
            lines.append(f"| `{r['feature']}` | {r['offset_min']:+d}min | "
                         f"{r['elite_mean']:.2f} | {r['failed_mean']:.2f} | "
                         f"{r['elite_mean']-r['failed_mean']:+.2f} | {r['cohens_d']:+.2f} |")
        lines.append("")

    # Feature-by-feature trajectory for the top 6 by max d
    top_feats_signed = lift.assign(absd=lift["cohens_d"].abs()) \
                            .groupby("feature")["absd"].max() \
                            .sort_values(ascending=False).head(8).index.tolist()
    lines.append("## Trajectories of top 8 features (mean by offset)")
    lines.append("")
    for feat in top_feats_signed:
        for direction in ("SELL", "BUY"):
            sub = traj[(traj["feature"]==feat) & (traj["direction"]==direction)]
            if sub.empty: continue
            lines.append(f"### `{feat}` — {direction}")
            lines.append("")
            lines.append("| Offset | ELITE | STRONG | ALL | WAFFLE | FAILED |")
            lines.append("|---|---|---|---|---|---|")
            for off in OFFSETS:
                so = sub[sub["offset_bars"]==off]
                def v(t):
                    r = so[so["tier"]==t]
                    return f"{r.iloc[0]['mean']:.2f}" if not r.empty else "-"
                lines.append(f"| {OFFSETS_MIN[off]:+d}min | {v('ELITE')} | "
                             f"{v('STRONG')} | {v('ALL')} | {v('WAFFLE')} | {v('FAILED')} |")
            lines.append("")

    with open(OUT_MD, "w") as f:
        f.write("\n".join(lines))
    print(f"\nreport → {OUT_MD}")


if __name__ == "__main__":
    main()
