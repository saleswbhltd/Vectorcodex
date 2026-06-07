"""
Step 37 — Per-type pivot engines.

Architecture:
  PivotEngine is a base class. Each subclass:
    - hunts ONE specific pivot type with a custom algorithm
    - returns candidate signal bars + a 0-1 quality score
    - is evaluated against ZZ-labeled pivots of its target type

The four engines:
  BuySwingEngine     → LL pivots (major reversal at lows)
  BuyPullbackEngine  → HL pivots (continuation in uptrend)
  SellSwingEngine    → HH pivots (major reversal at highs)
  SellPullbackEngine → LH pivots (continuation in downtrend)

Each engine has DIFFERENT detection logic — SWINGs use exhaustion at extremes,
PULLBACKs use trend + measured retracement.
"""

import pandas as pd
import numpy as np
from abc import ABC, abstractmethod

DATA = "/home/cmake/Vector/research/m5_with_h1.csv.gz"
PIP  = 0.0001
ZZ_THRESH = 20


# ════════════════════════════════════════════════════════════════════════
# Pivot ground truth (ZZ-labeled)
# ════════════════════════════════════════════════════════════════════════
def detect_pivots(df, thresh_pips):
    thresh = thresh_pips * PIP
    h = df["high"].values; l = df["low"].values; t = df.index.values
    direction_up = h[1] >= h[0]
    ext = h[1] if direction_up else l[1]; ext_i = 1
    out = []
    prev_h = None; prev_l = None
    for i in range(2, len(df)):
        if direction_up:
            if h[i] > ext: ext, ext_i = h[i], i
            elif l[i] <= ext - thresh:
                lbl = "H0" if prev_h is None else ("HH" if ext > prev_h else "LH")
                out.append((t[ext_i], lbl, ext)); prev_h = ext
                direction_up = False; ext, ext_i = l[i], i
        else:
            if l[i] < ext: ext, ext_i = l[i], i
            elif h[i] >= ext + thresh:
                lbl = "L0" if prev_l is None else ("HL" if ext > prev_l else "LL")
                out.append((t[ext_i], lbl, ext)); prev_l = ext
                direction_up = True; ext, ext_i = h[i], i
    return out


# ════════════════════════════════════════════════════════════════════════
# Base engine
# ════════════════════════════════════════════════════════════════════════
class PivotEngine(ABC):
    name = "BASE"; target_label = None; side = None
    def __init__(self, **params): self.params = params

    @abstractmethod
    def detect(self, df: pd.DataFrame) -> pd.DataFrame:
        """Returns DataFrame indexed by detection time with columns: score, type."""
        ...

    def score(self, mask: pd.Series, scores: pd.Series, target_mask: pd.Series,
              tol: int = 1) -> dict:
        """Precision/recall vs target ZZ pivots."""
        n_sig = int(mask.sum())
        if n_sig == 0:
            return {"signals": 0, "matches": 0, "real_pivots": int(target_mask.sum()),
                    "precision": 0, "recall": 0, "f1": 0,
                    "avg_score": 0}
        if tol > 0:
            piv_zone = target_mask.rolling(window=2*tol+1, center=True, min_periods=1).max() > 0
            sig_zone = mask.rolling(window=2*tol+1, center=True, min_periods=1).max() > 0
        else:
            piv_zone, sig_zone = target_mask, mask
        matches = int((mask & piv_zone).sum())
        covered = int((target_mask & sig_zone).sum())
        n_piv = int(target_mask.sum())
        prec = matches / n_sig
        rec = covered / n_piv if n_piv > 0 else 0
        f1 = 2*prec*rec/(prec+rec) if (prec+rec) > 0 else 0
        avg_s = float(scores[mask].mean()) if n_sig > 0 else 0
        return {"signals": n_sig, "matches": matches, "real_pivots": n_piv,
                "precision": prec, "recall": rec, "f1": f1, "avg_score": avg_s}


# ════════════════════════════════════════════════════════════════════════
# Engine 1: BUY_SWING — major reversal at lows
# Looks for EXHAUSTION at a new low after extended decline
# ════════════════════════════════════════════════════════════════════════
class BuySwingEngine(PivotEngine):
    name = "BUY_SWING_ENGINE"; target_label = "LL"; side = "BUY"
    def detect(self, df):
        p = self.params
        c, h, l, o = df["close"], df["high"], df["low"], df["open"]

        # Component conditions
        local_min  = df["low"] == df["low"].rolling(p.get("local_n", 10)).min()
        rsi_oversold = df["rsi14"] < p.get("rsi_max", 30)
        stoch_oversold = df["stoch_k"] < p.get("stoch_max", 20)
        williams_extreme = df["williams_r14"] < p.get("williams_max", -80)
        rejection_wick = df["lower_wick_ratio"] > p.get("min_wick", 0.30)
        below_ema = df["dist_ema50_atr"] < p.get("ema_dist_max", -1.0)
        # H1 also oversold gives extra weight
        h1_oversold = df["h1_rsi14"] < p.get("h1_rsi_max", 40)
        bb_lower = df["bb_pctB"] < p.get("bb_max", 0.20)
        # Recent decline (price moved down significantly into this bar)
        recent_decline = df["mom10_pips"] < p.get("mom_max", -10)

        # Score (0–8, but normalize to 0–1)
        score = (
            local_min.astype(int) +
            rsi_oversold.astype(int) +
            stoch_oversold.astype(int) +
            williams_extreme.astype(int) +
            rejection_wick.astype(int) +
            below_ema.astype(int) +
            h1_oversold.astype(int) +
            bb_lower.astype(int) +
            recent_decline.astype(int)
        ) / 9.0
        # Must satisfy hard gates
        hard = local_min & (df["rsi14"] < 35) & (df["lower_wick_ratio"] > 0.20)
        # Fire when both hard gate AND score above threshold
        thresh = p.get("score_threshold", 0.50)
        mask = hard & (score >= thresh)
        return pd.DataFrame({"score": score, "mask": mask}, index=df.index)


# ════════════════════════════════════════════════════════════════════════
# Engine 2: BUY_PULLBACK — continuation in uptrend
# Looks for measured retracement to support in established uptrend
# ════════════════════════════════════════════════════════════════════════
class BuyPullbackEngine(PivotEngine):
    name = "BUY_PULLBACK_ENGINE"; target_label = "HL"; side = "BUY"
    def detect(self, df):
        p = self.params
        c = df["close"]
        # Trend gates (must all be true)
        in_uptrend     = df["h1_above_ema50"] == 1
        h1_trend_up    = df["h1_ema50_slope_pips"] > p.get("h1_slope_min", 0)
        m5_above_ema50 = c > df["ema50"]
        adx_ok         = df["adx14"] > p.get("adx_min", 18)

        # Pullback signals (price dipped but not extreme)
        local_min      = df["low"] == df["low"].rolling(p.get("local_n", 8)).min()
        near_ema20     = df["dist_ema20_atr"].between(p.get("ema20_low", -1.5),
                                                       p.get("ema20_high", 0.5))
        rsi_pullback   = df["rsi14"].between(p.get("rsi_low", 35),
                                              p.get("rsi_high", 55))
        # Did the candle bounce? (close in upper half of bar)
        bounce_candle  = df["body_to_range"] > 0
        # Recent small dip (not catastrophic decline)
        recent_dip     = df["mom10_pips"].between(p.get("dip_low", -15),
                                                    p.get("dip_high", -3))

        score = (
            in_uptrend.astype(int) +
            h1_trend_up.astype(int) +
            m5_above_ema50.astype(int) +
            adx_ok.astype(int) +
            local_min.astype(int) +
            near_ema20.astype(int) +
            rsi_pullback.astype(int) +
            bounce_candle.astype(int) +
            recent_dip.astype(int)
        ) / 9.0
        # Hard gates: must be in uptrend AND at local low
        hard = in_uptrend & h1_trend_up & local_min
        thresh = p.get("score_threshold", 0.55)
        mask = hard & (score >= thresh)
        return pd.DataFrame({"score": score, "mask": mask}, index=df.index)


# ════════════════════════════════════════════════════════════════════════
# Engine 3: SELL_SWING — major reversal at highs
# ════════════════════════════════════════════════════════════════════════
class SellSwingEngine(PivotEngine):
    name = "SELL_SWING_ENGINE"; target_label = "HH"; side = "SELL"
    def detect(self, df):
        p = self.params
        local_max  = df["high"] == df["high"].rolling(p.get("local_n", 10)).max()
        rsi_overbought = df["rsi14"] > p.get("rsi_min", 70)
        stoch_overbought = df["stoch_k"] > p.get("stoch_min", 80)
        williams_extreme = df["williams_r14"] > p.get("williams_min", -20)
        rejection_wick = df["upper_wick_ratio"] > p.get("min_wick", 0.30)
        above_ema = df["dist_ema50_atr"] > p.get("ema_dist_min", 1.0)
        h1_overbought = df["h1_rsi14"] > p.get("h1_rsi_min", 60)
        bb_upper = df["bb_pctB"] > p.get("bb_min", 0.80)
        recent_rally = df["mom10_pips"] > p.get("mom_min", 10)

        score = (
            local_max.astype(int) +
            rsi_overbought.astype(int) +
            stoch_overbought.astype(int) +
            williams_extreme.astype(int) +
            rejection_wick.astype(int) +
            above_ema.astype(int) +
            h1_overbought.astype(int) +
            bb_upper.astype(int) +
            recent_rally.astype(int)
        ) / 9.0
        hard = local_max & (df["rsi14"] > 65) & (df["upper_wick_ratio"] > 0.20)
        thresh = p.get("score_threshold", 0.50)
        mask = hard & (score >= thresh)
        return pd.DataFrame({"score": score, "mask": mask}, index=df.index)


# ════════════════════════════════════════════════════════════════════════
# Engine 4: SELL_PULLBACK — continuation in downtrend
# ════════════════════════════════════════════════════════════════════════
class SellPullbackEngine(PivotEngine):
    name = "SELL_PULLBACK_ENGINE"; target_label = "LH"; side = "SELL"
    def detect(self, df):
        p = self.params
        c = df["close"]
        in_downtrend   = df["h1_above_ema50"] == 0
        h1_trend_dn    = df["h1_ema50_slope_pips"] < p.get("h1_slope_max", 0)
        m5_below_ema50 = c < df["ema50"]
        adx_ok         = df["adx14"] > p.get("adx_min", 18)

        local_max      = df["high"] == df["high"].rolling(p.get("local_n", 8)).max()
        near_ema20     = df["dist_ema20_atr"].between(p.get("ema20_low", -0.5),
                                                       p.get("ema20_high", 1.5))
        rsi_pullback   = df["rsi14"].between(p.get("rsi_low", 45),
                                              p.get("rsi_high", 65))
        rejection_candle = df["body_to_range"] < 0
        recent_rally   = df["mom10_pips"].between(p.get("rally_low", 3),
                                                    p.get("rally_high", 15))

        score = (
            in_downtrend.astype(int) +
            h1_trend_dn.astype(int) +
            m5_below_ema50.astype(int) +
            adx_ok.astype(int) +
            local_max.astype(int) +
            near_ema20.astype(int) +
            rsi_pullback.astype(int) +
            rejection_candle.astype(int) +
            recent_rally.astype(int)
        ) / 9.0
        hard = in_downtrend & h1_trend_dn & local_max
        thresh = p.get("score_threshold", 0.55)
        mask = hard & (score >= thresh)
        return pd.DataFrame({"score": score, "mask": mask}, index=df.index)


# ════════════════════════════════════════════════════════════════════════
# Evaluation
# ════════════════════════════════════════════════════════════════════════
def evaluate(engine, df, pivot_lookups, tol=1):
    """Run engine against the dataset; score against target type AND others."""
    result = engine.detect(df)
    mask = result["mask"]; scores = result["score"]
    target = pivot_lookups[engine.target_label]

    primary = engine.score(mask, scores, target, tol=tol)

    # How well does the engine confuse OTHER types?
    cross_results = {}
    for lbl, other in pivot_lookups.items():
        if lbl == engine.target_label: continue
        n_sig = int(mask.sum())
        if n_sig == 0:
            cross_results[lbl] = 0; continue
        if tol > 0:
            other_zone = other.rolling(window=2*tol+1, center=True, min_periods=1).max() > 0
        else:
            other_zone = other
        false_match = int((mask & other_zone & ~target).sum())
        cross_results[lbl] = false_match
    return primary, cross_results


def main():
    print("loading...")
    df = pd.read_csv(DATA, index_col=0, parse_dates=True)
    print(f"  bars: {len(df):,}")

    pivots = detect_pivots(df, ZZ_THRESH)
    print(f"  ZZ {ZZ_THRESH}pip pivots: {len(pivots)}")
    label_counts = pd.Series([p[1] for p in pivots]).value_counts()
    print(f"  label counts: {label_counts.to_dict()}")

    pivot_lookups = {}
    for lbl in ("HH", "HL", "LH", "LL"):
        times = [t for t, x, p in pivots if x == lbl]
        pivot_lookups[lbl] = pd.Series(df.index.isin(times), index=df.index)
        print(f"    {lbl}: {pivot_lookups[lbl].sum()} pivots")

    print(f"\n{'='*78}")
    print("PER-TYPE ENGINE EVALUATION (full dataset)")
    print(f"{'='*78}")

    engines = [
        BuySwingEngine(),
        BuyPullbackEngine(),
        SellSwingEngine(),
        SellPullbackEngine(),
    ]

    summary_rows = []
    for eng in engines:
        primary, cross = evaluate(eng, df, pivot_lookups, tol=1)
        print(f"\n— {eng.name}  (targets {eng.target_label} pivots)")
        print(f"  signals fired      : {primary['signals']}")
        print(f"  real {eng.target_label} pivots   : {primary['real_pivots']}")
        print(f"  matches            : {primary['matches']}")
        print(f"  precision (target) : {100*primary['precision']:.1f}%")
        print(f"  recall (target)    : {100*primary['recall']:.1f}%")
        print(f"  F1 (target)        : {primary['f1']:.3f}")
        print(f"  avg score          : {primary['avg_score']:.2f}")
        if cross:
            print(f"  false-firings vs other types (still pivots but wrong type):")
            for lbl, n in cross.items():
                print(f"    {lbl}: {n}")
        summary_rows.append({
            "engine": eng.name, "target": eng.target_label,
            "signals": primary["signals"], "matches": primary["matches"],
            "precision": primary["precision"], "recall": primary["recall"],
            "f1": primary["f1"],
        })

    pd.DataFrame(summary_rows).to_csv(
        "/home/cmake/Vector/research/engine_baseline.csv",
        index=False, float_format="%.4f")
    print(f"\nsaved → engine_baseline.csv")


if __name__ == "__main__":
    main()
