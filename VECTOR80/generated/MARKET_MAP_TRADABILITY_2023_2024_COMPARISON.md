# EURUSD Advanced Tradability Zones: 2023 vs 2024

Both years are built independently with the parity-audited canonical
steps 33, 34, 35 and 84, followed by the unchanged advanced tradability
feature, outcome, ranking and 15/30-minute aggregation methods.

## Important Definition

`Parent-confirmed` means a positive 15-minute zone has a positive 30-minute
parent with the same continuation/reversal archetype in that same year.
It is not OOS robustness because each annual map ranks and evaluates itself.

## Summary

- Positive 15-minute zones: `102` in 2023 and `135` in 2024.
- Parent-confirmed zones: `53` in 2023 and `77` in 2024.
- Exact parent-confirmed overlap: `18` (34.0% of the 2023 set).
- Exact overlap retaining the same strategy archetype: `10/18`.
- Parent-confirmed set Jaccard overlap: `16.1%`.
- 2023 parent-confirmed zones with a same-day/same-strategy 2024 zone within
  30 minutes: `52.8%`.
- Strategy-label agreement across all cells: `55.3%`.
- Quality-rank Spearman correlation: `0.774`.
- Selected-edge Spearman correlation: `0.655`.

## Exact Persistent Zones

| day | time | strategy_fit_2023 | selected_edge_2023 | selected_edge_2024 | best_quality_2023 | best_quality_2024 |
|---|---|---|---|---|---|---|
| Monday | 14:15 | REVERSAL | 0.444 | 1.444 | 79.142 | 86.218 |
| Friday | 12:45 | REVERSAL | 0.96 | 0.913 | 89.057 | 94.714 |
| Tuesday | 14:30 | REVERSAL | 0.907 | 0.767 | 91.282 | 88.761 |
| Thursday | 10:00 | REVERSAL | 0.543 | 0.765 | 81.457 | 87.41 |
| Wednesday | 13:15 | CONTINUATION | 0.596 | 0.606 | 97.166 | 80.053 |
| Monday | 13:00 | CONTINUATION | 0.692 | 0.448 | 90.503 | 89.687 |
| Tuesday | 14:45 | REVERSAL | 0.091 | 1.023 | 74.105 | 84.407 |
| Thursday | 10:15 | REVERSAL | 0.327 | 0.577 | 83.385 | 85.63 |
| Wednesday | 13:45 | CONTINUATION | 0.37 | 0.508 | 87.362 | 84.619 |
| Wednesday | 13:00 | CONTINUATION | 0.5 | 0.317 | 94.952 | 87.442 |
| Friday | 09:45 | REVERSAL | 0.434 | 0.35 | 83.242 | 80.228 |
| Monday | 13:45 | CONTINUATION | 0.537 | 0.229 | 91.335 | 91.25 |
| Friday | 11:30 | CONTINUATION | 0.563 | 0.178 | 76.721 | 69.089 |
| Monday | 11:45 | REVERSAL | 0.626 | 0.09 | 78.39 | 75.032 |
| Monday | 13:15 | CONTINUATION | 0.314 | 0.299 | 88.194 | 76.298 |
| Friday | 13:00 | CONTINUATION | 0.216 | 0.337 | 86.319 | 88.935 |
| Friday | 13:15 | CONTINUATION | 0.047 | 0.505 | 84.825 | 78.877 |
| Friday | 09:30 | REVERSAL | 0.312 | 0.112 | 77.738 | 78.077 |

## Nearby Time Shifts

| day | source_time | strategy | source_edge | nearest_target_time | distance_min | within_tolerance |
|---|---|---|---|---|---|---|
| Friday | 08:45 | REVERSAL | 0.29 | 09:00 | 15 | True |
| Friday | 12:30 | REVERSAL | 0.627 | 12:45 | 15 | True |
| Monday | 12:45 | CONTINUATION | 0.069 | 13:00 | 15 | True |
| Monday | 13:30 | CONTINUATION | 0.577 | 13:45 | 15 | True |
| Monday | 14:15 | REVERSAL | 0.444 | 14:30 | 15 | True |
| Thursday | 09:45 | REVERSAL | 0.438 | 10:00 | 15 | True |
| Thursday | 14:15 | CONTINUATION | 1.064 | 14:30 | 15 | True |
| Thursday | 19:30 | REVERSAL | 0.125 | 19:15 | 15 | True |
| Tuesday | 15:15 | REVERSAL | 0.499 | 15:00 | 15 | True |
| Wednesday | 12:15 | REVERSAL | 0.382 | 12:30 | 15 | True |
| Wednesday | 14:00 | CONTINUATION | 0.224 | 14:15 | 15 | True |
| Friday | 08:30 | REVERSAL | 0.21 | 09:00 | 30 | True |
| Friday | 09:30 | REVERSAL | 0.312 | 09:00 | 30 | True |
| Monday | 12:30 | CONTINUATION | 0.211 | 13:00 | 30 | True |
| Thursday | 17:15 | CONTINUATION | 1.26 | 16:45 | 30 | True |
| Thursday | 19:45 | REVERSAL | 0.051 | 19:15 | 30 | True |
| Wednesday | 12:00 | REVERSAL | 0.262 | 12:30 | 30 | True |
| Wednesday | 13:45 | CONTINUATION | 0.37 | 14:15 | 30 | True |

## Interpretation

- Exact overlap measures timetable stability; nearby overlap detects gradual
  movement that a fixed time-cell comparison would miss.
- Exact cells that switch continuation/reversal remain active windows, but
  their optimal strategy changed with the annual market regime.
- A weak edge correlation with a stronger quality correlation would mean the
  broad activity/liquidity structure persists while trade outcomes rotate.
- Changes can reflect macro regime, daylight behavior, provider-domain
  calibration stability and sampling noise, not only a permanent clock shift.
- These maps are descriptive annual studies. A zone must still validate in a
  later period before changing live thresholds.
