# MARKET_MAP Trend-Termination Study: 2024 Q4

This study asks whether an already-active bullish or bearish movement will
continue or terminate. Development uses 2023 through September 30, 2024.
The untouched three-month holdout is October 1 through December 31, 2024.

## Event Definition

- Active movement: trailing-hour BULL/BEAR direction, TREND or CHOP structure,
  and absolute displacement of at least `0.75 x ATR14`.
- Contiguous M5 rows with the same active direction are deduplicated to the
  first observation of each movement episode.
- Continuation: an additional favorable move of `max(2 pips, 0.75 x ATR14)`
  occurs before an adverse retracement of `max(2 pips, 0.50 x ATR14)`.
- Termination: the adverse retracement occurs first.
- Ambiguous paths reaching neither boundary are excluded.

## Holdout Performance

| horizon_min | test_rows | continue_rate | accuracy | balanced_accuracy | roc_auc |
|---|---|---|---|---|---|
| 15 | 1348 | 0.455 | 0.551 | 0.525 | 0.527 |
| 30 | 1647 | 0.461 | 0.539 | 0.5 | 0.518 |
| 60 | 1790 | 0.465 | 0.536 | 0.505 | 0.529 |

## Most Useful Features

| horizon_min | feature | importance | importance_std |
|---|---|---|---|
| 15 | atr14_pips | 0.015 | 0.008 |
| 15 | tick_count | 0.01 | 0.002 |
| 15 | current_range_expansion | 0.005 | 0.003 |
| 15 | time_sin | 0.005 | 0.005 |
| 15 | max_tick_interval_ms | 0.004 | 0.005 |
| 15 | vel_ratio_2nd_to_1st | 0.004 | 0.003 |
| 15 | median_tick_interval_ms | 0.003 | 0.001 |
| 15 | signed_body_to_range | 0.003 | 0.002 |
| 15 | rsi14 | 0.003 | 0.002 |
| 15 | atr_ratio_5_50 | 0.002 | 0.002 |
| 30 | atr14_pips | 0.019 | 0.007 |
| 30 | max_tick_interval_ms | 0.012 | 0.005 |
| 30 | plus_di | 0.005 | 0.002 |
| 30 | time_sin | 0.004 | 0.003 |
| 30 | vel_ratio_2nd_to_1st | 0.002 | 0.002 |
| 30 | current_efficiency | 0.002 | 0.003 |
| 30 | directional_exhaustion | 0.002 | 0.004 |
| 30 | adx14 | 0.001 | 0.003 |
| 30 | atr_ratio_5_50 | 0.001 | 0.002 |
| 30 | rsi14 | 0.001 | 0.001 |
| 60 | max_tick_interval_ms | 0.01 | 0.002 |
| 60 | atr14_pips | 0.009 | 0.005 |
| 60 | minus_di | 0.007 | 0.004 |
| 60 | current_range_expansion | 0.007 | 0.003 |
| 60 | spread_avg | 0.006 | 0.005 |
| 60 | velocity_change | 0.005 | 0.001 |
| 60 | vol_of_vol_20 | 0.004 | 0.002 |
| 60 | tick_count | 0.004 | 0.005 |
| 60 | bb_pctB | 0.004 | 0.002 |
| 60 | signed_body_to_range | 0.003 | 0.004 |

## Monday Morning 06:00-10:00 UTC

| horizon_min | direction | volatility | episodes | continuation_rate | ci95_low | ci95_high |
|---|---|---|---|---|---|---|
| 15 | BEAR | EXPANSION | 16 | 0.438 | 0.231 | 0.668 |
| 15 | BEAR | NORMAL | 11 | 0.636 | 0.354 | 0.848 |
| 15 | BULL | EXPANSION | 18 | 0.5 | 0.29 | 0.71 |
| 15 | BULL | NORMAL | 11 | 0.545 | 0.28 | 0.787 |
| 30 | BEAR | EXPANSION | 16 | 0.438 | 0.231 | 0.668 |
| 30 | BEAR | NORMAL | 11 | 0.636 | 0.354 | 0.848 |
| 30 | BULL | EXPANSION | 19 | 0.474 | 0.273 | 0.683 |
| 30 | BULL | NORMAL | 12 | 0.583 | 0.32 | 0.807 |
| 60 | BEAR | EXPANSION | 16 | 0.438 | 0.231 | 0.668 |
| 60 | BEAR | NORMAL | 11 | 0.636 | 0.354 | 0.848 |
| 60 | BULL | EXPANSION | 19 | 0.474 | 0.273 | 0.683 |
| 60 | BULL | NORMAL | 12 | 0.583 | 0.32 | 0.807 |

Detailed strength-band breakdown:

| current_direction_label | strength_band | current_volatility_label | rows | continuation_rate | predicted_rate | efficiency | range_expansion | horizon_min |
|---|---|---|---|---|---|---|---|---|
| BEAR | EXTREME | NORMAL | 1 | 1.0 | 0.374 | 0.5 | 1.079 | 15 |
| BULL | EXTREME | NORMAL | 2 | 1.0 | 0.521 | 0.498 | 1.014 | 15 |
| BEAR | MODERATE | NORMAL | 4 | 0.75 | 0.436 | 0.121 | 1.165 | 15 |
| BULL | STRONG | EXPANSION | 6 | 0.667 | 0.441 | 0.235 | 1.691 | 15 |
| BULL | STRONG | NORMAL | 3 | 0.667 | 0.583 | 0.321 | 1.132 | 15 |
| BEAR | STRONG | EXPANSION | 12 | 0.5 | 0.471 | 0.235 | 1.899 | 15 |
| BEAR | STRONG | NORMAL | 6 | 0.5 | 0.434 | 0.287 | 1.074 | 15 |
| BULL | MODERATE | EXPANSION | 10 | 0.5 | 0.465 | 0.15 | 1.952 | 15 |
| BULL | MODERATE | NORMAL | 6 | 0.333 | 0.442 | 0.163 | 1.168 | 15 |
| BEAR | MODERATE | EXPANSION | 4 | 0.25 | 0.571 | 0.138 | 1.649 | 15 |
| BULL | EXTREME | EXPANSION | 2 | 0.0 | 0.544 | 0.508 | 1.999 | 15 |
| BEAR | EXTREME | NORMAL | 1 | 1.0 | 0.444 | 0.5 | 1.079 | 30 |
| BULL | EXTREME | NORMAL | 3 | 1.0 | 0.445 | 0.465 | 1.014 | 30 |
| BEAR | MODERATE | NORMAL | 4 | 0.75 | 0.451 | 0.121 | 1.165 | 30 |
| BULL | STRONG | EXPANSION | 6 | 0.667 | 0.446 | 0.235 | 1.691 | 30 |
| BULL | STRONG | NORMAL | 3 | 0.667 | 0.459 | 0.321 | 1.132 | 30 |
| BEAR | STRONG | EXPANSION | 12 | 0.5 | 0.45 | 0.235 | 1.899 | 30 |
| BEAR | STRONG | NORMAL | 6 | 0.5 | 0.441 | 0.287 | 1.074 | 30 |
| BULL | MODERATE | EXPANSION | 11 | 0.455 | 0.449 | 0.151 | 1.923 | 30 |
| BULL | MODERATE | NORMAL | 6 | 0.333 | 0.451 | 0.163 | 1.168 | 30 |
| BEAR | MODERATE | EXPANSION | 4 | 0.25 | 0.465 | 0.138 | 1.649 | 30 |
| BULL | EXTREME | EXPANSION | 2 | 0.0 | 0.44 | 0.508 | 1.999 | 30 |
| BEAR | EXTREME | NORMAL | 1 | 1.0 | 0.449 | 0.5 | 1.079 | 60 |
| BULL | EXTREME | NORMAL | 3 | 1.0 | 0.454 | 0.465 | 1.014 | 60 |
| BEAR | MODERATE | NORMAL | 4 | 0.75 | 0.458 | 0.121 | 1.165 | 60 |
| BULL | STRONG | EXPANSION | 6 | 0.667 | 0.44 | 0.235 | 1.691 | 60 |
| BULL | STRONG | NORMAL | 3 | 0.667 | 0.46 | 0.321 | 1.132 | 60 |
| BEAR | STRONG | EXPANSION | 12 | 0.5 | 0.473 | 0.235 | 1.899 | 60 |
| BEAR | STRONG | NORMAL | 6 | 0.5 | 0.449 | 0.287 | 1.074 | 60 |
| BULL | MODERATE | EXPANSION | 11 | 0.455 | 0.455 | 0.151 | 1.923 | 60 |
| BULL | MODERATE | NORMAL | 6 | 0.333 | 0.46 | 0.163 | 1.168 | 60 |
| BEAR | MODERATE | EXPANSION | 4 | 0.25 | 0.484 | 0.138 | 1.649 | 60 |
| BULL | EXTREME | EXPANSION | 2 | 0.0 | 0.401 | 0.508 | 1.999 | 60 |

## Interpretation

- ROC AUC measures ranking skill, not certainty. A result near 0.50 has no
  useful discrimination; 0.60-0.65 is modest filter value.
- Strength alone cannot identify an exact top. Strong efficient trends can
  continue, while extreme expansion plus declining velocity may signal ending.
- Time should be treated as context interacting with strength and volatility,
  not as a standalone directional prediction.
- Monday-morning confidence intervals are wide because the quarter contains
  only 56-58 independent decisive episodes. These figures are hypotheses for
  another holdout, not threshold settings.
- Adjacent M5 events overlap. Results describe state-filter quality, not a
  sequence of independent trades. Episode deduplication reduces, but does not
  eliminate, dependence between nearby market movements.
