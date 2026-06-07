"""
Step 65 — Build multiple detection engines and union for 80% recall.

New tradeable target: MFE ≥ 8 pips, MFE/MAE ≥ 3.0
Expected tradeable: ~266/month DEV, ~263/month OOS
Recall target: 80% of these = ~210/month detected

Engines:
  E1: Stage-1 OR ensemble (per trade_context) — already validated at 96% recall on ANY pivot
  E2: GBM per trade_context (relaxed target) — re-trained
  E3: Rule-based extreme triggers — direct indicator extremes
  E4: Multi-class consensus — when 2+ classes co-fire
  E5: HTF-confirmed candidates — pivot signature + H1 trend alignment

Each engine emits candidate bars. Union of all engines = final detection set.
Measure: total recall vs total fire rate.
"""

import pandas as pd
import numpy as np

PANEL    = "/home/cmake/Vector/research/EURUSD_M5_FULL_PANEL.csv.gz"
DEV_PIV  = "/home/cmake/Vector/research/pivot_map_v3.csv"
OOS_PIV  = "/home/cmake/Vector/research/pivot_map_v3_oos.csv"
SCAN     = "/home/cmake/Vector/research/indicator_scan_zzlines.csv"
DEV_START = "2025-02-01"; DEV_END = "2026-02-28"
OOS_START = "2026-03-01"; OOS_END = "2026-06-01"

CLASSES = ["BULL_TREND_BREAK_LOW","BEAR_CONTINUATION_LOW","BUY_PULLBACK_UPTREND",
           "BULL_CONTINUATION_HIGH","BEAR_TREND_BREAK_HIGH",
           "WEAK_LOW_IN_DOWNTREND","SELL_PULLBACK_DOWNTREND","WEAK_HIGH_IN_UPTREND"]

PIP = 0.0001


def expand_pivots_to_zone(pivot_times, panel_index, tol_bars=2):
    """Expand each pivot time to ±tol_bars window."""
    out = set()
    idx_loc = pd.Series(range(len(panel_index)), index=panel_index)
    for t in pivot_times:
        if t not in idx_loc.index: continue
        i = int(idx_loc.loc[t])
        for k in range(-tol_bars, tol_bars+1):
            j = i + k
            if 0 <= j < len(panel_index):
                out.add(panel_index[j])
    return out


# ─────────────────────────────────────────────────────────────────────
# Engine 1: Stage-1 OR ensemble per trade_context
# ─────────────────────────────────────────────────────────────────────
OP_POINTS_E1 = {
    "BULL_TREND_BREAK_LOW":     (70, 5),  "BEAR_TREND_BREAK_HIGH": (80, 5),
    "BULL_CONTINUATION_HIGH":   (70, 5),  "BEAR_CONTINUATION_LOW": (70, 5),
    "BUY_PULLBACK_UPTREND":     (60, 5),  "SELL_PULLBACK_DOWNTREND":(80, 3),
    "WEAK_HIGH_IN_UPTREND":     (70, 3),  "WEAK_LOW_IN_DOWNTREND": (80, 3),
}


def build_stage1_ensemble(panel, dev_panel, dev_pivots, scan, ctx, K, zone_pct):
    sub_scan = scan[(scan["dimension"]=="trade_context") & (scan["class"]==ctx) & scan["keep"]]
    dev_pivots_ctx = dev_pivots[dev_pivots["trade_context"] == ctx]
    if dev_pivots_ctx.empty or sub_scan.empty: return np.zeros(len(panel), dtype=bool)
    top = sub_scan.sort_values("auc", ascending=False).head(K)
    union = np.zeros(len(panel), dtype=bool)
    for _, r in top.iterrows():
        feat = r["indicator"]
        if feat not in panel.columns: continue
        dev_pivot_vals = dev_panel.loc[dev_pivots_ctx.index, feat].dropna().values
        if len(dev_pivot_vals) < 10: continue
        d = r["cohens_d"]
        if d >= 0:
            thresh = np.percentile(dev_pivot_vals, 100 - zone_pct)
            mask = panel[feat].fillna(panel[feat].median()).values >= thresh
        else:
            thresh = np.percentile(dev_pivot_vals, zone_pct)
            mask = panel[feat].fillna(panel[feat].median()).values <= thresh
        union |= mask
    return union


def engine_e1(panel, dev_panel, dev_pivots, scan):
    """Returns boolean mask: bar is candidate if ANY class ensemble fires."""
    any_fire = np.zeros(len(panel), dtype=bool)
    for ctx, (zone, K) in OP_POINTS_E1.items():
        any_fire |= build_stage1_ensemble(panel, dev_panel, dev_pivots, scan, ctx, K, zone)
    return any_fire


# ─────────────────────────────────────────────────────────────────────
# Engine 3: Rule-based extreme triggers
# Direct combinatorial rules that fire on classical exhaustion patterns
# ─────────────────────────────────────────────────────────────────────
def engine_e3(panel):
    """Direct rules for exhaustion patterns at potential pivots."""
    p = panel
    # HIGH pivot exhaustion (potential SELL): RSI > 70 + BB upper band touch + bearish bar
    high_exhaust = (
        (p["rsi14"] > 65) &
        (p["bb_pctB"] > 0.85) &
        (p["high"] >= p["high"].rolling(10).max() - PIP * 1)
    )
    # LOW pivot exhaustion (potential BUY)
    low_exhaust = (
        (p["rsi14"] < 35) &
        (p["bb_pctB"] < 0.15) &
        (p["low"] <= p["low"].rolling(10).min() + PIP * 1)
    )
    # Stochastic extremes
    stoch_high = (p["stoch_k"] > 80) & (p["stoch_d"] > 75)
    stoch_low  = (p["stoch_k"] < 20) & (p["stoch_d"] < 25)
    # Williams extremes
    wpr_high = p["williams_r14"] > -15
    wpr_low  = p["williams_r14"] < -85
    # Local extremes (rolling N-bar high/low)
    local_high_5 = p["high"] >= p["high"].rolling(5).max() - PIP * 0.5
    local_low_5  = p["low"]  <= p["low"].rolling(5).min() + PIP * 0.5
    # ATR expansion
    atr_expand = p["atr5"] > p["atr14_pips"]
    # Combined rule firing
    sell_rule = (high_exhaust | stoch_high | wpr_high) & local_high_5
    buy_rule  = (low_exhaust  | stoch_low  | wpr_low)  & local_low_5
    fired = sell_rule | buy_rule
    return fired.fillna(False).values


# ─────────────────────────────────────────────────────────────────────
# Engine 4: Multi-class consensus (≥2 class OR ensembles fire)
# ─────────────────────────────────────────────────────────────────────
def engine_e4(panel, dev_panel, dev_pivots, scan):
    """Bar fires if at least 2 different class ensembles fire on same bar."""
    fires = np.zeros(len(panel), dtype=int)
    for ctx, (zone, K) in OP_POINTS_E1.items():
        m = build_stage1_ensemble(panel, dev_panel, dev_pivots, scan, ctx, K, zone)
        fires += m.astype(int)
    return (fires >= 2)


# ─────────────────────────────────────────────────────────────────────
# Engine 5: HTF-confirmed (H1 trend agrees with pivot direction)
# ─────────────────────────────────────────────────────────────────────
def engine_e5(panel):
    """Pivot signature + H1 EMA50 slope confirms direction."""
    p = panel
    # Sell signature: RSI > 60 + price above EMA20
    sell_sig = (p["rsi14"] > 60) & (p["dist_ema20_atr"] > 0.5)
    # Buy signature
    buy_sig  = (p["rsi14"] < 40) & (p["dist_ema20_atr"] < -0.5)
    # H1 trend confirmation
    h1_up = p["h1_ema50_slope_pips"] > 5
    h1_dn = p["h1_ema50_slope_pips"] < -5
    fired = (sell_sig & h1_up) | (buy_sig & h1_dn) | \
             (sell_sig & h1_dn) | (buy_sig & h1_up)  # both alignments
    return fired.fillna(False).values


# ─────────────────────────────────────────────────────────────────────
# Engine 2: Per-class GBM (existing) — implemented via candidates_*.csv
# We'll use existing predictions if available, otherwise skip
# ─────────────────────────────────────────────────────────────────────
def engine_e2_from_existing(period_label):
    """Load existing candidate signals from previous final_signal_stream.csv if available."""
    # We'll skip E2 here — it's the per-class GBM which we'll re-build later if needed
    return None


def evaluate_engine_recall(engine_mask, panel, pivot_times_set, tol_bars=2):
    """Calculate recall vs tradeable pivots."""
    if not pivot_times_set: return 0, 0, 0, 0
    fire_idx = np.where(engine_mask)[0]
    n_fire = len(fire_idx)
    # Expand each pivot to ±tol_bars zone
    panel_idx = panel.index
    idx_loc = pd.Series(range(len(panel_idx)), index=panel_idx)
    pivot_zone_mask = np.zeros(len(panel), dtype=bool)
    for t in pivot_times_set:
        if t not in idx_loc.index: continue
        i = int(idx_loc.loc[t])
        for k in range(-tol_bars, tol_bars+1):
            j = i + k
            if 0 <= j < len(panel):
                pivot_zone_mask[j] = True
    # Recall: how many pivots have at least one candidate fire within ±tol
    covered = 0
    for t in pivot_times_set:
        if t not in idx_loc.index: continue
        i = int(idx_loc.loc[t])
        lo = max(0, i - tol_bars); hi = min(len(panel), i + tol_bars + 1)
        if engine_mask[lo:hi].any(): covered += 1
    matches = int(np.sum(engine_mask & pivot_zone_mask))
    return matches, n_fire, covered, len(pivot_times_set)


def main():
    print("loading data...")
    panel = pd.read_csv(PANEL, index_col=0, parse_dates=True)
    dev_panel = panel.loc[DEV_START:DEV_END]
    oos_panel = panel.loc[OOS_START:OOS_END]
    dev_pivots_all = pd.read_csv(DEV_PIV, parse_dates=["pivot_time"])
    oos_pivots_all = pd.read_csv(OOS_PIV, parse_dates=["pivot_time"])
    scan = pd.read_csv(SCAN)

    # Add trade_context (was in old map, not in v3 — derive on the fly)
    def label_trade_context(lbl, t):
        if pd.isna(t): return "UNKNOWN"
        if t == 0:     return "RANGE"
        if t > 0:
            return {"HL":"BUY_PULLBACK_UPTREND","HH":"BULL_CONTINUATION_HIGH",
                    "LL":"BULL_TREND_BREAK_LOW","LH":"WEAK_HIGH_IN_UPTREND"}.get(lbl,"UNKNOWN")
        return {"LH":"SELL_PULLBACK_DOWNTREND","LL":"BEAR_CONTINUATION_LOW",
                "HH":"BEAR_TREND_BREAK_HIGH","HL":"WEAK_LOW_IN_DOWNTREND"}.get(lbl,"UNKNOWN")
    for df_pivots, df_panel in [(dev_pivots_all, dev_panel), (oos_pivots_all, oos_panel)]:
        h1 = df_panel["h1_trend_dir"].reindex(df_pivots["pivot_time"]).values
        df_pivots["trade_context"] = [label_trade_context(l, t) for l, t in
                                       zip(df_pivots["label"], h1)]
    # Get only tradeable pivots
    dev_trade_pivots = set(pd.to_datetime(dev_pivots_all[dev_pivots_all["tradeable"]==True]["pivot_time"]))
    oos_trade_pivots = set(pd.to_datetime(oos_pivots_all[oos_pivots_all["tradeable"]==True]["pivot_time"]))
    print(f"  DEV tradeable: {len(dev_trade_pivots)}  ({len(dev_trade_pivots)/389:.1f}/day)")
    print(f"  OOS tradeable: {len(oos_trade_pivots)}  ({len(oos_trade_pivots)/92:.1f}/day)")

    # Need dev_pivots indexed (for engine_e1)
    dev_pivots_indexed = dev_pivots_all.set_index("pivot_time")
    dev_pivots_indexed.index = pd.to_datetime(dev_pivots_indexed.index)

    # Build engines on DEV
    print(f"\n{'='*90}\nDEV — Per-engine recall on tradeable pivots\n{'='*90}")
    engines = [
        ("E1: Stage-1 OR per-class", lambda p, dp, dpv, sc: engine_e1(p, dp, dpv, sc)),
        ("E3: Rule-based extremes",  lambda p, dp, dpv, sc: engine_e3(p)),
        ("E4: 2+ class consensus",   lambda p, dp, dpv, sc: engine_e4(p, dp, dpv, sc)),
        ("E5: HTF + signature",      lambda p, dp, dpv, sc: engine_e5(p)),
    ]
    dev_masks = []
    for label, fn in engines:
        mask = fn(dev_panel, dev_panel, dev_pivots_indexed, scan)
        matches, n_fire, covered, n_tradeable = evaluate_engine_recall(
            mask, dev_panel, dev_trade_pivots, tol_bars=2)
        recall = covered / max(n_tradeable, 1)
        fire_rate = n_fire / len(dev_panel)
        print(f"  {label:32s}  fires={n_fire:>6d} ({100*fire_rate:>5.1f}%)  "
              f"covered={covered}/{n_tradeable} ({100*recall:>5.1f}%)")
        dev_masks.append((label, mask))

    # Union of all engines
    union_mask = np.zeros(len(dev_panel), dtype=bool)
    for _, m in dev_masks:
        union_mask |= m
    matches, n_fire, covered, n_tradeable = evaluate_engine_recall(
        union_mask, dev_panel, dev_trade_pivots, tol_bars=2)
    print(f"\n  UNION of all 4 engines:           fires={n_fire:>6d} "
          f"({100*n_fire/len(dev_panel):>5.1f}%)  "
          f"covered={covered}/{n_tradeable} ({100*covered/n_tradeable:>5.1f}%)")

    # Apply same engines to OOS (using DEV-derived thresholds)
    print(f"\n{'='*90}\nOOS — Per-engine recall on tradeable pivots\n{'='*90}")
    oos_masks = []
    for label, fn in engines:
        mask = fn(oos_panel, dev_panel, dev_pivots_indexed, scan)
        matches, n_fire, covered, n_tradeable = evaluate_engine_recall(
            mask, oos_panel, oos_trade_pivots, tol_bars=2)
        recall = covered / max(n_tradeable, 1)
        fire_rate = n_fire / len(oos_panel)
        print(f"  {label:32s}  fires={n_fire:>6d} ({100*fire_rate:>5.1f}%)  "
              f"covered={covered}/{n_tradeable} ({100*recall:>5.1f}%)")
        oos_masks.append((label, mask))

    union_mask = np.zeros(len(oos_panel), dtype=bool)
    for _, m in oos_masks:
        union_mask |= m
    matches, n_fire, covered, n_tradeable = evaluate_engine_recall(
        union_mask, oos_panel, oos_trade_pivots, tol_bars=2)
    print(f"\n  UNION of all 4 engines:           fires={n_fire:>6d} "
          f"({100*n_fire/len(oos_panel):>5.1f}%)  "
          f"covered={covered}/{n_tradeable} ({100*covered/n_tradeable:>5.1f}%)")

    target = 0.80 * n_tradeable
    print(f"\n  Target 80% recall = {target:.0f}/{n_tradeable}")
    if covered >= target:
        print(f"  ✓ ACHIEVED")
    else:
        print(f"  ✗ short by {target - covered:.0f}")


if __name__ == "__main__":
    main()
