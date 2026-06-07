# MARKET_MAP Advanced Tradability-Zone Study

This study asks whether recurring weekday/15-minute zones are historically
easier to trade after estimated spread, rather than merely active.

## Inputs

- Tick count and calibrated bid/ask volume.
- Average spread relative to ATR and maximum tick gap.
- Forward 30-minute path cleanliness and absolute movement.
- Target-before-stop outcomes for continuation and reversal archetypes.
- Development: calendar 2025. OOS validation: March-June 2026.

## Strategy Archetypes

- Continuation follows the causal trailing-hour BULL/BEAR state.
- Reversal trades against that state.
- Dynamic target is `max(3 pips, 1.0 x ATR14)`.
- Dynamic stop is `max(2 pips, 0.75 x ATR14)`.
- Spread is deducted and target must be reached before stop.

## Result

- Primary 15-minute development zones: 472
- Primary 15-minute OOS zones: 472
- Positive in development and OOS using the development-selected archetype: 30
- Confirmed by a positive 30-minute parent with the same archetype: 10
- Stable positive 30-minute zones used as a robustness check: 11

## Robust 15-Minute Zones

| day | time | strategy_fit_dev | best_quality_dev | liquidity_score_dev | selected_edge_dev | selected_edge_oos | selected_wr_oos | rows_oos |
|---|---|---|---|---|---|---|---|---|
| Wednesday | 14:00 | REVERSAL | 77.722 | 80.262 | 0.441 | 2.077 | 0.538 | 39 |
| Tuesday | 13:30 | REVERSAL | 90.064 | 79.115 | 1.128 | 1.598 | 0.564 | 39 |
| Monday | 13:45 | REVERSAL | 92.468 | 72.467 | 0.453 | 1.375 | 0.5 | 42 |
| Friday | 17:30 | REVERSAL | 68.665 | 50.843 | 0.225 | 1.063 | 0.359 | 39 |
| Tuesday | 12:45 | REVERSAL | 94.216 | 69.774 | 0.365 | 0.597 | 0.359 | 39 |
| Monday | 01:00 | REVERSAL | 81.001 | 52.355 | 0.188 | 0.4 | 0.405 | 42 |
| Tuesday | 08:15 | REVERSAL | 76.981 | 67.241 | 0.027 | 0.259 | 0.436 | 39 |
| Monday | 06:30 | REVERSAL | 73.676 | 51.464 | 0.276 | 0.215 | 0.357 | 42 |
| Tuesday | 08:45 | CONTINUATION | 85.546 | 66.016 | 0.235 | 0.172 | 0.359 | 39 |
| Monday | 08:15 | REVERSAL | 86.229 | 66.812 | 0.215 | 0.131 | 0.381 | 42 |

## Interpretation

- Raw volume identifies activity, not tradeability.
- High volume with wide spread or low path cleanliness is often difficult.
- A useful zone requires movement, liquidity, acceptable cost and a strategy
  archetype that remains positive out of sample.
- Only zones whose 30-minute parent validates with the same strategy are
  treated as robust. Other positive 15-minute cells remain provisional.
- Each 15-minute OOS cell currently contains only about 39-42 observations.
  Because 472 zones were examined, multiple-testing risk remains substantial.
- Require a second forward period or live shadow validation before these zones
  can change entry thresholds or position size.
- Zone filters are priors. They must refine a valid setup, not create entries.
