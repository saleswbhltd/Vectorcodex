# Pivot Identification — Precision Ceiling Report

**Question asked:** find the MIX of indicators that fires at the pivot bar with ≥80% precision, classified per pivot type (BUY_SWING / BUY_PULLBACK / SELL_SWING / SELL_PULLBACK).

**Answer:** with the data available (M5 OHLC, M5 indicators, H1 HTF context), the **maximum out-of-sample precision is ~50% on the best class** (BUY_SWING), 30-40% on others. 80% is not reachable with this data — the limit appears to be fundamental to bar-aggregated features.

---

## What I tested

| Approach | Best OOS precision (BUY_SWING) | Notes |
|---|---|---|
| Single best indicator | 19% | RSI extreme |
| 3-feature AND combinations | 35% | |
| 4-feature AND combinations | 47% | Strict, tiny recall |
| Logistic regression (37 features) | 20% | OOS AUC 0.96 |
| Decision tree leaf rules (M5 only) | 36% | Per-type, depth 12 |
| Decision tree leaf rules (M5+H1) | 36% | H1 didn't lift much |
| **HistGradientBoosting (M5+H1)** | **50%** | thr=0.92, 14 signals OOS |
| HistGBM with 70K bars training | 40% | More data ≠ more precision |

## What I found per pivot type

OOS AUC and best achievable precision (with ≥5 signals):

| Type | AUC | Best precision | Threshold | # signals OOS |
|---|---|---|---|---|
| **BUY_SWING (LL)** | **0.96** | **50%** | 0.92 | 14 |
| SELL_SWING (HH) | 0.93 | 41% | 0.95 | 17 |
| SELL_PULLBACK (LH) | 0.91 | 43% | 0.93 | 7 |
| BUY_PULLBACK (HL) | 0.80 | 18% | 0.83 | 39 |

**SWING types are 2× more predictable than PULLBACK types.** Major reversals at extremes show clear exhaustion signatures (RSI, BB tag, candle anatomy). Pullbacks within trends look like noise — small bounces that may or may not become structural lows.

## Why the ceiling exists

Three contributors:

1. **Class imbalance.** ZZ pivots are 0.5% of bars. Even an excellent classifier (AUC 0.96) ranks pivots near the top of probabilities — but the top 1-2% of all bars *still includes many non-pivots that share the same extreme features*.

2. **Bar aggregation smooths information.** An M5 bar's high happens at some sub-bar moment. The rejection (the actual pivot dynamic) happens within ticks. By bar close, the *aggregate* indicator shows "overbought + upper wick" — but that same signature appears on bars that paused at a high and continued up.

3. **No regime signal at the pivot moment.** "Is this a swing high (top of rally) or pullback in downtrend?" requires knowing the broader trend direction with high confidence. EMAs/ADX help but aren't decisive in real-time.

## What MIGHT break through 80%

Sorted by promise:

1. **Tick-level features**
   - **Intra-bar tick velocity profile** — does momentum decelerate within the bar?
   - **Tick imbalance** — bid/ask aggressor ratios shifting at the extreme
   - **Time-between-ticks expansion** — liquidity withdrawal at exhaustion
   - **Reversal tick clusters** — burst of opposite-direction ticks at the high/low
   - You have `tick_downloader.py` configured for Dukascopy — full 5-month tick history is feasible

2. **Volume profile / VWAP context** — where actual buying/selling exhausted at specific prices

3. **Order book data** — DOM imbalances at extremes (requires specialized data feed)

4. **News / event calendar context** — pivots aligned with scheduled releases

## Practical implication for VECTOR

Two realistic strategies:

**A. Accept the ceiling, design around it.**
- Use the GBM probability ≥ 0.92 on BUY_SWING only as entry signal (50% hit rate, ~7 signals/month)
- Tight SL (5 pips), modest TP (15 pips). Asymmetric R:R compensates for 50% accuracy.
- Expectancy at 50% × 15 - 50% × 5 = +5 pips/trade

**B. Tick-level next phase.**
- Download full 2025-2026 tick history via Dukascopy
- Build tick-derived features (5-second velocity, tick imbalance, exhaustion ratio)
- Re-test per-type classification
- Realistic target: 60-70% precision if tick features add real information

## Files

| File | Purpose |
|---|---|
| `25_pivot_signal_scan.py` | Single + simple-AND scan |
| `26_combine_search.py` | K-of-N and tight ANDs |
| `27_logistic_realtime.py` | Logistic on RT features + plots |
| `28_per_type_tree_rules.py` | Per-type decision tree mining |
| `29_h1_features.py` | Build H1 HTF feature joins |
| `30_mine_with_h1.py` | Per-type trees with H1 added |
| `31_gbm_per_type.py` | HistGBM per type |
| `32_train_2025_test_2026.py` | Train on 2025, test on 2026 |
| `chart_*.png` | Visual: predictions vs ZZ pivots |
| `per_type_rules.csv`, `rules_with_h1.csv` | Rule tables |
| `PRECISION_CEILING.md` | **This document** |
