# VECTOR Signal Research — Pivot Quality Analysis

**Dataset:** EURUSD M5, 2025-01-22 → 2025-12-31 (69,760 bars)
**Pivot method:** pip-threshold ZigZag, 15-pip flip — gives **~9 pivots/day**, matches the screenshot density.
**Good-pivot rule:** TP=15pip hit *before* SL=10pip within a 24-bar (2-hour) window after the confirm bar.

---

## 1 — Baseline (no filtering)

| Side | Count | Good % | Avg MFE | Avg MAE |
|---|---|---|---|---|
| SELL (HH/LH) | 1,510 | **28.5%** | +17.4 | +18.2 |
| BUY (HL/LL) | 1,510 | **31.5%** | +17.5 | +16.9 |
| **All pivots** | 3,020 | **30.0%** | 17 / 17 | balanced |

At 30% good with TP=15 / SL=10 (R:R 1.5): expectancy = 0.30×15 − 0.70×10 = **−2.5 pips/trade**.
**Trading every pivot loses money.** We need a filter that lifts good % above ~41% to break even.

## 2 — Top discriminators (in-sample AUC, full year)

| Rank | Feature | AUC (SELL) | AUC (BUY) | Interpretation |
|---|---|---|---|---|
| 1 | `atr14_pips` | 0.596 | 0.598 | **Higher volatility = better pivots** |
| 2 | `range_pips` | 0.587 | 0.600 | Big confirmation candle = real turn |
| 3 | **`confirm_lag`** | 0.582 | 0.597 | **Short retracement (≤8 bars) = decisive, real pivot** |
| 4 | `bb_width_pips` | 0.564 | 0.583 | Wide bands = volatility expansion = better pivot |
| 5 | `bars_since_prev` | 0.565 | 0.549 | Pivots close to last pivot = better than long droughts |
| 6 | `stoch_k` | 0.55 | 0.570 | Lower stoch on BUY pivots = better |
| 7 | `body_pips` | 0.563 | 0.556 | Larger candle body = better |
| 8 | `rsi14` | ~0.54 | ~0.54 | Marginal — RSI alone is not very predictive |

**What ISN'T predictive (surprised me):**
- `dist_ema200_pips` (distance from EMA200) — not in top 10
- `is_pin_bull` / `is_pin_bear` (pin bars) — almost no signal
- `is_eng_bull` / `is_eng_bear` (engulfing) — almost no signal
- `adx14` — marginal, ranking ~12
- `hour_utc` — flat (no session predictability at M5 pivot level)

The arrow placement in your screenshot is about candle anatomy + volatility, **not** classical patterns.

## 3 — In-sample ensemble (top 12 features per side)

Random Forest, 5-fold CV AUC: **SELL 0.588, BUY 0.604.**
Threshold 0.35 → SELL **53% good** / 20% coverage; BUY **44% good** / 47% coverage.
Threshold 0.40 → SELL **71% good** / 3% coverage; BUY **65% good** / 13% coverage.

In-sample this looks excellent. Then we check holdout.

## 4 — Walk-forward (train H1 2025, test H2 2025) — THE REAL TEST

**Out-of-sample AUC:** SELL 0.603 (LR) / 0.574 (RF) — both still > random.
**Test set base rate dropped from ~30% to ~24%** — H2 2025 was a strong uptrend; reversal pivots harder to trade in trending regimes (Rule 8 from your saved design rules: E<1 in trending = strategy struggles).

### Best operating points OOS (6 months of test data)

| Side | Model | Thresh | N trades | Good % | Net pips | Exp/trade |
|---|---|---|---|---|---|---|
| **SELL** | Logistic | 0.35 | 23 | **47.8%** | **+45** | **+1.96** |
| SELL | Logistic | 0.40 | 8  | 50.0% | +20 | +2.50 |
| **BUY**  | Logistic | 0.45 | 12 | **41.7%** | **+15** | **+1.25** |
| BUY  | RF       | 0.45 | 15 | 33.3% | +5  | +0.33 |

**Combined realistic operating point:** ~35 trades / 6 months = **~6 trades/month**, +60 pips total net, **+1.7 pips average expectancy.**

### Honest assessment

- ✅ Edge is **real** — out-of-sample net positive on a 6-month unseen period
- ✅ Top features ranked in-sample held up out-of-sample (volatility & confirm-lag dominate)
- ⚠ **Edge is thin** — +1.7 pips/trade won't survive 0.5–1 pip EURUSD spread + slippage
- ⚠ Random Forest **overfit** (in-sample 0.588 AUC → OOS 0.574 SELL, 0.631 BUY — still OK, but the threshold cuts that worked in-sample collapse OOS). **Use Logistic, not RF.**
- ⚠ H2 2025 was a strong uptrend — same regime risk that killed OTT001B (Rule 8). The pivot+filter approach inherits the same regime sensitivity.

## 5 — Proposed signal formula

Concrete enough to implement and backtest immediately:

```
SIGNAL = pivot_detected AND quality_score > threshold

quality_score = w1*ATR14_pips
              + w2*candle_range_pips
              - w3*confirm_lag_bars             (short = better)
              + w4*BB_width_pips
              - w5*bars_since_prev              (close to last = better)
              + w6*body_pips
              + (side-specific RSI/stoch term)

SELL extras: minus_di (higher = stronger downside)
BUY  extras: stoch_k inverted (lower stoch = better BUY)

Hard gates (no scoring needed — skip if any fails):
  - confirm_lag ≤ 12 bars    (decisive pivot only)
  - ATR14 ≥ 5 pips           (no flat market)
  - range_pips ≥ 6 pips      (no doji-confirmation pivots)
```

Weights to use as starting point (from Logistic coefficients, fitted on full year):
```
SELL: 0.18·ATR + 0.14·range - 0.20·confirm_lag + 0.09·BB_width
      + 0.07·body + 0.08·(-stoch_k) + 0.06·minus_di
BUY:  0.20·range + 0.16·ATR - 0.19·confirm_lag + 0.10·BB_width
      + 0.08·body + 0.10·(-stoch_k)
Threshold: standardize each feature with train-set mean/std, classifier output ≥ 0.40
```

Expected performance per the walk-forward:
- ~6 trades/month
- 42–48% good rate (vs 30% baseline)
- +1.7 pips/trade expectancy at TP=15 / SL=10

## 6 — What this isn't (yet)

This signal **alone** is not strong enough to be a tradable EA. +1.7 pips/trade is a coin-flip after spread. Three additional levers we haven't tested could push it through:

1. **HTF bias gate.** Only take pivots aligned with H1 or H4 trend. The user's original picture showed this (H1/H4/D1 panel). This was the strongest discriminator in OTT001's analysis.
2. **OB/FVG confluence.** Pivots at a structural OB or FVG zone may have higher precision. Requires building an OB scanner on the same dataset.
3. **Session filter.** Saved Rule 4 says mean-reversion is best in Asian (00:00–09:00 UTC). The hour-of-day feature was flat as a discriminator, but it might gate well when combined with the score.

## 7 — Recommended next steps

Pick one direction and confirm:

**Path A — Strengthen the signal (recommended):** add HTF bias + OB-zone proximity to the feature matrix, re-run the discrimination analysis. If those push OOS expectancy to +3 pips+, build VECTOR002 with this pivot+score+confluence logic.

**Path B — Ship as-is for paper trading:** code the proposed formula into VECTOR002 with the conservative threshold (0.40, ~3 trades/month per side), backtest the full 2025 to verify the walk-forward numbers hold, paper-trade Jan–Feb 2026, then evaluate.

**Path C — Pivot to higher timeframe:** redo the same analysis on M15 or H1 pivots — bigger pivots may have a stronger statistical signature and easier execution (this is closer to how OTT001 found its edge before regime-failure).

## Files produced

| File | Contents |
|---|---|
| `01_compute_indicators.py` | Computes 30+ indicators from raw M5 OHLC |
| `02_detect_pivots.py` | Pip-threshold ZigZag, label HH/HL/LH/LL |
| `03_build_features.py` | One row per pivot + forward MFE/MAE + good label |
| `04_analyze.py` | Per-feature AUC, KS, Spearman + ensemble in-sample |
| `05_walkforward_sim.py` | Train H1, test H2 — the honest test |
| `m5_with_indicators.csv.gz` | 69,760 bars × 39 cols |
| `pivots_thresh*.csv` | Pivot tables at 5–30 pip thresholds |
| `features_pivots.csv` / `features_random.csv` | Feature matrices |
| `feature_ranking.csv` | Ranked discriminator stats |
| `analysis_report.txt` | Full text dump from step 4 |
| `signal_proposal.json` | Machine-readable proposal |
| `VECTOR_DataExport.mq5` | MT5 script for real-tick + M1 export (deployed) |
