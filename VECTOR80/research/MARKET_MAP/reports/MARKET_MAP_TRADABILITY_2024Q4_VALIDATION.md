# MARKET_MAP Tradability Historical Holdout: 2024 Q4

This is an independent three-month historical validation of frozen calendar
2025 tradability-zone definitions on broker-adjusted Dukascopy M5 features.
It is reverse-time validation, not forward OOS, because the holdout predates
the development period.
This parity-safe run supersedes the initial 2024 Q4 result.

## Period

- Start: `2024-10-01` UTC, inclusive.
- End: `2025-01-01` UTC, exclusive.
- Valid M5 observations grouped into 15-minute zones: `18416`.
- September 2024 data is retained only as causal indicator warm-up.

## Frozen Contract

- Panel construction reproduces canonical research steps 33, 34, 35 and 84
  for all fields used by the tradability study.
- The script-34 four-decimal intermediate serialization is reproduced before
  canonical script-35 indicators are calculated.
- ATR14 uses the same Wilder-style exponential smoothing as the 2025 panel.
- Tick calibration is applied after panel construction, in the same order as
  canonical script 84.
- Zone quality and continuation/reversal choice come only from calendar 2025.
- Dynamic target: `max(3 pips, 1.0 x ATR14)`.
- Dynamic stop: `max(2 pips, 0.75 x ATR14)`.
- Outcome horizon: next 30 minutes; spread is included.
- Fifteen-minute zones require matching positive 30-minute parent behavior
  to receive robust confirmation.

## Results

- Frozen 2025 positive-edge 15-minute candidates: `88`.
- Positive again in 2024 Q4: `36` (40.9%).
- Weighted mean holdout edge across all 88 candidates: `-0.291 pips` per M5 entry.
- Also confirmed by the 30-minute parent: `14`.
- Original 2025 + 2026 robust zones positive in 2024 Q4: `7/10`.
- Weighted mean holdout edge across those 10 robust zones: `+0.350 pips` per M5 entry.

## Parent-Confirmed Replications

| day | time | strategy_fit_dev | best_quality_dev | selected_edge_dev | selected_edge_oos | selected_wr_oos | rows_oos |
|---|---|---|---|---|---|---|---|
| Wednesday | 14:00 | REVERSAL | 77.722 | 0.441 | 2.024 | 0.389 | 36 |
| Wednesday | 12:45 | REVERSAL | 79.772 | 0.207 | 1.723 | 0.472 | 36 |
| Tuesday | 08:45 | CONTINUATION | 85.546 | 0.235 | 1.365 | 0.548 | 42 |
| Wednesday | 14:15 | REVERSAL | 87.362 | 0.026 | 1.342 | 0.306 | 36 |
| Monday | 08:15 | REVERSAL | 86.229 | 0.215 | 1.186 | 0.487 | 39 |
| Tuesday | 08:15 | REVERSAL | 76.981 | 0.027 | 0.856 | 0.429 | 42 |
| Friday | 14:15 | CONTINUATION | 94.746 | 0.419 | 0.705 | 0.308 | 39 |
| Friday | 11:45 | REVERSAL | 79.306 | 0.025 | 0.479 | 0.385 | 39 |
| Friday | 17:45 | REVERSAL | 69.55 | 0.124 | 0.438 | 0.282 | 39 |
| Tuesday | 12:45 | REVERSAL | 94.216 | 0.365 | 0.433 | 0.333 | 42 |
| Friday | 11:30 | REVERSAL | 80.26 | 0.402 | 0.317 | 0.282 | 39 |
| Friday | 17:30 | REVERSAL | 68.665 | 0.225 | 0.238 | 0.308 | 39 |
| Monday | 07:45 | CONTINUATION | 91.96 | 0.332 | 0.202 | 0.308 | 39 |
| Tuesday | 08:00 | REVERSAL | 84.693 | 0.295 | 0.043 | 0.357 | 42 |

## Original Robust-Zone External Check

| day | time | strategy_fit_dev | selected_edge_oos | selected_wr_oos | rows_oos |
|---|---|---|---|---|---|
| Wednesday | 14:00 | REVERSAL | 2.024 | 0.389 | 36 |
| Tuesday | 08:45 | CONTINUATION | 1.365 | 0.548 | 42 |
| Monday | 08:15 | REVERSAL | 1.186 | 0.487 | 39 |
| Tuesday | 08:15 | REVERSAL | 0.856 | 0.429 | 42 |
| Tuesday | 12:45 | REVERSAL | 0.433 | 0.333 | 42 |
| Monday | 13:45 | REVERSAL | 0.372 | 0.385 | 39 |
| Friday | 17:30 | REVERSAL | 0.238 | 0.308 | 39 |
| Monday | 06:30 | REVERSAL | -0.679 | 0.256 | 39 |
| Monday | 01:00 | REVERSAL | -0.768 | 0.154 | 39 |
| Tuesday | 13:30 | REVERSAL | -1.384 | 0.214 | 42 |

## Interpretation

- A three-month cell normally contains 12-14 weekday dates and 36-42 M5
  entries, so individual time cells remain noisy.
- The broad positive-development candidate list failed as a portfolio; its
  average holdout edge was negative. Quality ranking alone is insufficient.
- The previously narrowed 10-zone robust set replicated materially better,
  supporting 30-minute parent confirmation and repeated-period validation.
- Broad replication rate matters more than one unusually profitable cell.
- Thirty-minute outcomes from entries five minutes apart overlap. Edge values
  describe filter quality and must not be read as independent trade returns.
- Prices and quoted volume are Dukascopy. Fifteen microstructure fields are
  mapped to the RoboForex feature domain using the 2025-2026 overlap.
- That backward calibration is a domain-transfer assumption and prevents this
  sample from being called genuine historical RoboForex OOS data.
- Zones should remain setup filters, not independent entry signals.

## Method Audit

- The reference HTML in `C:/Users/cmake/Documents` is byte-identical to the
  project-generated 2025-2026 map.
- A direct raw-tick comparison against canonical script 34 matched 575/576
  extracted bars at four-decimal precision. The sole mismatch was the first
  sliced bar lacking its preceding tick.
- The yearly builder now carries the preceding monthly tick forward, matching
  continuous-stream interval and aggressor calculations at month boundaries.
- The same `add_forward_outcomes`, 15/30-minute aggregation, frozen ranking,
  strategy selection and parent-confirmation functions are used.
