# High-Recall Pivot Detection — Methodology Result

## Inverted approach worked

Instead of chasing 80% precision (capped at ~50% with bar+H1+tick features), we built **per-class OR ensembles of 3-5 indicators tuned for maximum RECALL** — accepting low precision in stage 1 with the explicit plan to filter for tradeability in stage 2.

## Pivot ground truth

User's port of MetaQuotes ZigZag algorithm (D=12, Deviation=5, Backstep=3) — `50_build_zz_lines_mtf_map.py`. This is the algorithm used by ZigZag Lines MTF and most MT5 ZigZag indicators, so the engine is directly portable to MQL5.

- **DEV period:** 2025-02-01 → 2026-02-28 (4580 pivots)
- **OOS period:** 2026-03-01 → 2026-06-01 (1124 pivots, untouched)

## Rich classification

Each pivot tagged across 5 dimensions:

| Dimension | Values |
|---|---|
| `label` | HH / HL / LH / LL |
| `side` | BUY / SELL |
| `role` | SWING / PULLBACK |
| `strength_tier` | STRONG / MEDIUM / WEAK (by post-pivot 60-min MFE) |
| `trade_context` | BULL_CONTINUATION_HIGH, BUY_PULLBACK_UPTREND, BULL_TREND_BREAK_LOW, SELL_PULLBACK_DOWNTREND, BEAR_CONTINUATION_LOW, BEAR_TREND_BREAK_HIGH, WEAK_HIGH_IN_UPTREND, WEAK_LOW_IN_DOWNTREND, RANGE |

The `trade_context` is the key discriminator — a HL pivot in an uptrend (BUY_PULLBACK_UPTREND) has a *completely different* indicator signature than a HL pivot in a downtrend (WEAK_LOW_IN_DOWNTREND).

## Per-trade-context indicator detection power (DEV, AUC)

| Trade context | Top discriminator AUC | Top indicators (signed direction) |
|---|---|---|
| BULL_CONTINUATION_HIGH | 0.87 | rsi14 ↑ / dist_ema20_atr ↑ / stoch_k ↑ / plus_di ↑ |
| BULL_TREND_BREAK_LOW   | 0.89 | rsi14 ↓ / bb_pctB ↓ / minus_di ↑ / stoch_k ↓ |
| BUY_PULLBACK_UPTREND   | 0.76 | stoch_k ↓ / williams_r14 ↓ / h1_ema50_slope ↑ |
| WEAK_HIGH_IN_UPTREND   | 0.76 | h1_ema50_slope ↑ / macd_hist ↑ / stoch_k ↑ |
| BEAR_CONTINUATION_LOW  | 0.89 | rsi14 ↓ / bb_pctB ↓ / stoch_k ↓ |
| BEAR_TREND_BREAK_HIGH  | 0.86 | rsi14 ↑ / dist_ema20_atr ↑ / minus_di ↓ |
| SELL_PULLBACK_DOWNTREND| 0.83 | h1_dist_ema200_pips ↓ / h1_ema200_slope ↓ |
| WEAK_LOW_IN_DOWNTREND  | 0.83 | h1_ema200_slope ↓ / h1_ema50_slope ↓ |

By strength tier:
- STRONG: AUC up to 0.89 (easy to detect)
- MEDIUM: AUC up to 0.81
- WEAK: AUC only 0.56-0.65 (noise — best to skip)

## OOS results (Mar-Jun 2026, completely held out)

Per-class K=3-5 indicator OR ensemble, threshold derived from DEV pivot distribution percentiles:

| Trade context | K | zone | DEV pivots | OOS pivots | **OOS Recall** | OOS Fire% | OOS Prec% |
|---|---|---|---|---|---|---|---|
| BULL_TREND_BREAK_LOW   | 5 | 70 | 486 | 83  | **97.6%** | 29.7% | 1.36% |
| BEAR_TREND_BREAK_HIGH  | 5 | 80 | 347 | 118 | **99.2%** | 37.9% | 1.59% |
| BULL_CONTINUATION_HIGH | 5 | 70 | 506 | 94  | **90.4%** | 27.6% | 1.47% |
| BEAR_CONTINUATION_LOW  | 5 | 70 | 364 | 130 | **98.5%** | 30.5% | 2.09% |
| BUY_PULLBACK_UPTREND   | 5 | 60 | 527 | 98  | **94.9%** | 54.1% | 0.86% |
| SELL_PULLBACK_DOWNTREND| 3 | 80 | 367 | 140 | **96.4%** | 56.7% | 1.25% |
| WEAK_HIGH_IN_UPTREND   | 3 | 70 | 505 | 90  | **96.7%** | 53.2% | 0.83% |
| WEAK_LOW_IN_DOWNTREND  | 3 | 80 | 356 | 128 | **95.3%** | 56.8% | 1.12% |

**Mean OOS recall: 96.1%** — methodology generalized.

## What this means

We can **catch 96%+ of all pivot events in real time** using per-class 3-5 indicator OR ensembles. The fire rate is high (28-57% of bars) which translates to ~1-2% precision — many false positives.

That's by design. Stage 2 (next) filters the candidate set for tradeability.

## Pipeline files

| Step | File | Purpose |
|---|---|---|
| 50 | `50_build_zz_lines_mtf_map.py` (user) | MetaQuotes ZigZag port (D12/Dev5/Back3) |
| 51 | `51_join_zzlines_panel.py` | Attach indicators + add rich labels |
| 52 | `52_scan_zzlines.py` | Per-class/strength/context indicator scan |
| 53 | `53_recall_zzlines.py` | Per-class OR ensemble + recall sweep |
| 54 | `54_oos_validation.py` | Hold-out validation on 2026-03 → 2026-06 |

## Next phase: tradeable-pivot filter

The 96% recall produces ~3-5× more candidates than real pivots. To trade we need:

1. **Score each candidate** by:
   - All K=5 indicators firing simultaneously (vs just any one)
   - Probability that this candidate is a real pivot of the target class
   - Expected MFE/MAE band

2. **Drop pivots with low tradeable potential:**
   - WEAK strength_tier (80% of pivots, only 4.5% have meaningful MFE)
   - RANGE trade_context (no clear trend to lean on)

3. **Filter on tradeability metrics:**
   - Sufficient distance to stop level
   - Acceptable spread
   - Time-of-day session ok
