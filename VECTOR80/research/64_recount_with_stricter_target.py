"""
Step 64 — Re-label tradeable with MFE/MAE ≥ 3.0 and validate per-day pivot count.

User expects 5-8 good pivots/day on M5 EURUSD. Test multiple MFE thresholds
combined with R:R ≥ 3.0 (was 1.5) to find the right target definition.
"""

import pandas as pd
import numpy as np

PANEL    = "/home/cmake/Vector/research/EURUSD_M5_FULL_PANEL.csv.gz"
ZZ_FULL  = "/home/cmake/Vector/research/EURUSD_M5_ZZLINES_D12_Dev5_Back3_FULL_AVAILABLE_pivot_map.csv"
OUT_DEV  = "/home/cmake/Vector/research/pivot_map_v3.csv"
OUT_OOS  = "/home/cmake/Vector/research/pivot_map_v3_oos.csv"

DEV_START = "2025-02-01"
DEV_END   = "2026-02-28"
OOS_START = "2026-03-01"
OOS_END   = "2026-06-01"

PIP = 0.0001
LOOKAHEAD_BARS = 12

# Test multiple tradeable definitions
DEFINITIONS = [
    {"name": "MFE6_R3",  "mfe_min": 6,  "rr": 3.0},
    {"name": "MFE8_R3",  "mfe_min": 8,  "rr": 3.0},
    {"name": "MFE10_R3", "mfe_min": 10, "rr": 3.0},
    {"name": "MFE12_R3", "mfe_min": 12, "rr": 3.0},
    {"name": "MFE8_R2",  "mfe_min": 8,  "rr": 2.0},
    {"name": "MFE10_R2", "mfe_min": 10, "rr": 2.0},
    # Reference: previous
    {"name": "MFE12_R1.5_prev", "mfe_min": 12, "rr": 1.5},
]


def compute_excursions(panel_df, pivots_df, mfe_min):
    """For each pivot, compute mfe_60m, mae_60m, and first-hit ordering."""
    H = panel_df["high"].values; L = panel_df["low"].values
    panel_idx = pd.Series(range(len(panel_df)), index=panel_df.index)
    res = []
    for _, p in pivots_df.iterrows():
        if p["pivot_time"] not in panel_idx.index:
            res.append((np.nan, np.nan, np.nan, np.nan)); continue
        i = int(panel_idx.loc[p["pivot_time"]])
        end = min(i + LOOKAHEAD_BARS, len(panel_df))
        is_high = (p["side"] == "HIGH")
        ref = p["price"]
        mfe = 0.0; mae = 0.0
        mfe_hit = None; mae_hit = None
        for k, j in enumerate(range(i+1, end), start=1):
            if is_high:
                fav = (ref - L[j]) / PIP; adv = (H[j] - ref) / PIP
            else:
                fav = (H[j] - ref) / PIP; adv = (ref - L[j]) / PIP
            if fav > mfe: mfe = fav
            if adv > mae: mae = adv
            if mfe_hit is None and fav >= mfe_min: mfe_hit = k
            # MAE threshold for "first hit" = mfe_min/rr (so SL distance scales with R:R)
            # We'll compute multiple variants below
        res.append((mfe, mae, mfe_hit, None))
    return res


def main():
    print("loading...")
    panel = pd.read_csv(PANEL, index_col=0, parse_dates=True)
    pivots = pd.read_csv(ZZ_FULL, parse_dates=["pivot_time"])
    pivots = pivots[pivots["label"].isin(["HH","HL","LH","LL"])].copy()

    def process_period(panel_p, pivots_p, period_name):
        days = (panel_p.index.max() - panel_p.index.min()).days
        print(f"\n=== {period_name} ({len(pivots_p)} pivots, {days} days = {len(pivots_p)/days:.1f}/day) ===")
        print(f"  base ZZ pivot density: {len(pivots_p)/days:.1f}/day")

        # Compute MFE/MAE/first-hit once (use highest MFE threshold for hit computation)
        res = compute_excursions(panel_p, pivots_p, mfe_min=6)
        pivots_p = pivots_p.copy()
        pivots_p["mfe_60m"] = [r[0] for r in res]
        pivots_p["mae_60m"] = [r[1] for r in res]
        # For each definition, count tradeable
        print(f"\n  {'definition':25s} {'tradeable':>9s} {'/day':>6s} {'/month':>7s} {'rate%':>6s}")
        for d in DEFINITIONS:
            mfe_min = d["mfe_min"]; rr = d["rr"]
            mae_max = mfe_min / rr
            # Recompute first-hit for this mfe_min/mae_max
            mfe_first = []; mae_first = []
            for _, p in pivots_p.iterrows():
                if pd.isna(p["mfe_60m"]):
                    mfe_first.append(np.nan); mae_first.append(np.nan); continue
                # Re-walk window for this threshold
                H = panel_p["high"].values; L = panel_p["low"].values
                pidx = pd.Series(range(len(panel_p)), index=panel_p.index)
                i = int(pidx.loc[p["pivot_time"]])
                end = min(i + LOOKAHEAD_BARS, len(panel_p))
                is_high = (p["side"] == "HIGH"); ref = p["price"]
                m_hit = None; a_hit = None
                for k, j in enumerate(range(i+1, end), start=1):
                    fav = (ref - L[j]) / PIP if is_high else (H[j] - ref) / PIP
                    adv = (H[j] - ref) / PIP if is_high else (ref - L[j]) / PIP
                    if m_hit is None and fav >= mfe_min: m_hit = k
                    if a_hit is None and adv >= mae_max: a_hit = k
                    if m_hit is not None and a_hit is not None: break
                mfe_first.append(m_hit if m_hit is not None else np.nan)
                mae_first.append(a_hit if a_hit is not None else np.nan)
            # Tradeable: MFE hit AND (MAE not hit, OR MFE before MAE)
            def is_tradeable(mfe, mae, m_hit, a_hit):
                if pd.isna(mfe): return False
                if mfe < mfe_min: return False
                if mae > 0 and (mfe / mae) < rr: return False
                if pd.isna(m_hit): return False
                if not pd.isna(a_hit) and a_hit <= m_hit: return False
                return True
            trade_count = sum(is_tradeable(pivots_p["mfe_60m"].iloc[i],
                                            pivots_p["mae_60m"].iloc[i],
                                            mfe_first[i], mae_first[i])
                              for i in range(len(pivots_p)))
            rate = 100 * trade_count / len(pivots_p)
            per_day = trade_count / max(days, 1)
            per_month = per_day * 30
            print(f"  {d['name']:25s} {trade_count:>8d} {per_day:>5.1f} {per_month:>6.0f}  {rate:>5.1f}%")

        # Save the v3 (MFE/MAE ≥ 3.0, MFE ≥ 8) version
        primary_def = {"mfe_min": 8, "rr": 3.0}
        mfe_first = []; mae_first = []
        for _, p in pivots_p.iterrows():
            if pd.isna(p["mfe_60m"]):
                mfe_first.append(np.nan); mae_first.append(np.nan); continue
            H = panel_p["high"].values; L = panel_p["low"].values
            pidx = pd.Series(range(len(panel_p)), index=panel_p.index)
            i = int(pidx.loc[p["pivot_time"]])
            end = min(i + LOOKAHEAD_BARS, len(panel_p))
            is_high = (p["side"] == "HIGH"); ref = p["price"]
            m_hit = None; a_hit = None
            for k, j in enumerate(range(i+1, end), start=1):
                fav = (ref - L[j]) / PIP if is_high else (H[j] - ref) / PIP
                adv = (H[j] - ref) / PIP if is_high else (ref - L[j]) / PIP
                if m_hit is None and fav >= primary_def["mfe_min"]: m_hit = k
                if a_hit is None and adv >= primary_def["mfe_min"]/primary_def["rr"]: a_hit = k
                if m_hit is not None and a_hit is not None: break
            mfe_first.append(m_hit if m_hit is not None else np.nan)
            mae_first.append(a_hit if a_hit is not None else np.nan)
        pivots_p["mfe_first_hit"] = mfe_first
        pivots_p["mae_first_hit"] = mae_first
        pivots_p["tradeable"] = [
            (not pd.isna(m) and m >= primary_def["mfe_min"] and
             a > 0 and (m/a) >= primary_def["rr"] and
             not pd.isna(mh) and (pd.isna(ah) or ah > mh))
            for m, a, mh, ah in zip(pivots_p["mfe_60m"], pivots_p["mae_60m"], mfe_first, mae_first)
        ]
        return pivots_p

    dev_panel = panel.loc[DEV_START:DEV_END]
    dev_pivots = pivots[(pivots["pivot_time"] >= DEV_START) & (pivots["pivot_time"] <= DEV_END)].copy()
    dev_out = process_period(dev_panel, dev_pivots, "DEV (2025-02 → 2026-02)")

    oos_panel = panel.loc[OOS_START:OOS_END]
    oos_pivots = pivots[(pivots["pivot_time"] >= OOS_START) & (pivots["pivot_time"] <= OOS_END)].copy()
    oos_out = process_period(oos_panel, oos_pivots, "OOS (2026-03 → 2026-06)")

    # Save primary version
    dev_out.to_csv(OUT_DEV, index=False, float_format="%.5f")
    oos_out.to_csv(OUT_OOS, index=False, float_format="%.5f")
    print(f"\nsaved primary tradeable defs (MFE≥8, MFE/MAE≥3.0):")
    print(f"  DEV → {OUT_DEV}")
    print(f"  OOS → {OUT_OOS}")


if __name__ == "__main__":
    main()
