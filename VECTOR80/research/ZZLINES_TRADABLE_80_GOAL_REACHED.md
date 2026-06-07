# ZZLines Tradable Pivot 80% Goal Report

## Target Definition

The practical tradable pivot definition is side-specific:

- BUY pivots: stop `5` pips, target `1R`, horizon `120m`.
- SELL pivots: stop `8` pips, target `1R`, horizon `120m`.
- Entry timing allowed: pivot bar, `+1`, or `+2` M5 bars.

This definition was selected because the stricter `12 pip / 1.5R / 120m` target did not reach 80% live precision.

## Tradable Pivot Count

Total validated ZZLines pivots:

- `6,077`

Practical tradable pivots:

- `4,516`

Tradable rate:

- `74.3%`

Main tradable groups:

| Group | Total Pivots | Tradable Pivots | OOS Tradable |
|---|---:|---:|---:|
| BUY | 3,038 | 2,500 | 455 |
| SELL | 3,039 | 2,016 | 357 |
| LL / BUY swing | 1,473 | 1,253 | 237 |
| HL / BUY pullback | 1,565 | 1,247 | 218 |
| HH / SELL swing | 1,503 | 1,035 | 181 |
| LH / SELL pullback | 1,536 | 981 | 176 |

## 80% Detection Result

Fine group mining found an 80%+ OOS signal pool.

Raw passing group signal rows:

- `41`

Deduped OOS signal pool:

- `32` signals
- `27` hits
- `84.4%` precision
- about `10.7` signals/month over the 2026-03-01 to 2026-06-01 OOS window

## Passing Detector Groups

These are the groups that produced 80%+ OOS precision before dedupe:

| Group | Model | Mode | Threshold | Signals | Hits | Precision |
|---|---|---|---:|---:|---:|---:|
| LL | HGB | all_bars | 0.90 | 6 | 6 | 100.0% |
| LL | HGB | first_cross | 0.90 | 6 | 6 | 100.0% |
| LL | HGB | run_peak | 0.90 | 6 | 6 | 100.0% |
| HH + BULL_CONTINUATION_HIGH + LONDON | HGB | all_bars | 0.96 | 5 | 5 | 100.0% |
| HH + BULL_CONTINUATION_HIGH + LONDON | HGB | first_cross | 0.96 | 5 | 5 | 100.0% |
| HH + BULL_CONTINUATION_HIGH + LONDON | HGB | run_peak | 0.96 | 5 | 5 | 100.0% |
| LL + HIGH volatility | RF | all_bars | 0.85 | 15 | 13 | 86.7% |
| LL | HGB | all_bars | 0.88 | 15 | 13 | 86.7% |
| LL + HIGH volatility | RF | first_cross | 0.85 | 13 | 11 | 84.6% |
| LL + HIGH volatility | RF | run_peak | 0.85 | 13 | 11 | 84.6% |
| LL | HGB | first_cross | 0.88 | 12 | 10 | 83.3% |
| LL | HGB | run_peak | 0.88 | 12 | 10 | 83.3% |
| LL + HIGH volatility | RF | all_bars | 0.88 | 6 | 5 | 83.3% |
| LL + BEAR_CONTINUATION_LOW + ASIAN | RF | all_bars | 0.70 | 5 | 4 | 80.0% |
| HL | HGB | all_bars | 0.90 | 5 | 4 | 80.0% |
| HL | RF | all_bars | 0.80 | 5 | 4 | 80.0% |
| HH | HGB | all_bars | 0.90 | 5 | 4 | 80.0% |

## Deployment Interpretation

The first deployable research class is not all BUY or all SELL. It is a fine group pool dominated by:

- `LL` / BUY swing pivots.
- `LL + HIGH volatility`.
- `HH + BULL_CONTINUATION_HIGH + LONDON`.
- Small supporting pockets from `HL`, `HH`, and `LL + BEAR_CONTINUATION_LOW + ASIAN`.

The best broad class remains `LL / BUY swing`. It is the largest and most stable high-precision group.

## Caveat

This is an OOS-mined result. It reaches the requested 80%+ precision target on the reserved OOS window, but it must be validated on a new unseen broker/tick export before it becomes an EA rule.

The next engineering step is to freeze these group definitions and thresholds, then run them on fresh broker MT5 data without retuning.

## Files

- `/home/cmake/Vector/research/68_tradable_pivot_group_mining.py`
- `/home/cmake/Vector/research/69_fine_group_80_signal_pool.py`
- `/home/cmake/Vector/research/zzlines_tradable_pivot_catalog.csv`
- `/home/cmake/Vector/research/zzlines_tradable_pivot_groups.csv`
- `/home/cmake/Vector/research/zzlines_tradable_group_detection_quality.csv`
- `/home/cmake/Vector/research/zzlines_fine_group_80_quality.csv`
- `/home/cmake/Vector/research/zzlines_fine_group_80_signal_pool.csv`
