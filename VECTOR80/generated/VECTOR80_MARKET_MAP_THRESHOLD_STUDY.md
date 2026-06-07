# VECTOR80 + MARKET_MAP Adaptive Threshold Study

## Question

Can MARKET_MAP identify conditions where VECTOR80 model thresholds can be
lowered to add trades without materially reducing signal quality?

## Design

- VECTOR80 models, engine groups, stops, targets and published 42-signal
  baseline are frozen.
- MARKET_MAP uses only trailing completed-bar direction, structure and
  volatility state. No future MARKET_MAP labels are used.
- Policy discovery: March 1-April 30, 2026.
- Untouched policy holdout: May 1-June 1, 2026.
- Tested threshold reductions: 0.01, 0.02, 0.03, 0.05, 0.08 and 0.10.
- Added candidates are blocked within 30 minutes of a published same-side
  signal and deduplicated with the same 30-minute same-side interval.
- Discovery acceptance requires at least 4 added signals, at least 75%
  added precision and combined precision no more than 3 percentage points
  below the frozen baseline.

Below-threshold candidates examined: `512`.

## Baseline

- DISCOVERY: `32` signals, `28` hits, `87.5%` precision.
- HOLDOUT: `10` signals, `8` hits, `80.0%` precision.

## Discovery Result

`1` policy settings passed discovery. Their holdout results are shown below.

| Policy | Delta | Added | Added precision | Combined precision | Increase |
|---|---:|---:|---:|---:|---:|
| OPPOSING_CHOP_EXPANSION | 0.01 | 4 | 75.0% | 86.1% | 12.5% |

## Holdout

| Policy | Delta | Added | Added precision | Combined precision | Increase |
|---|---:|---:|---:|---:|---:|
| OPPOSING_CHOP_EXPANSION | 0.01 | 0 | n/a | 80.0% | 0.0% |

## Conclusion

- The only discovery-qualified policy added no holdout trades.
- It failed the objective of increasing trade count on unseen data.
  Keep all VECTOR80 thresholds unchanged.
- `OPPOSING_CHOP_EXPANSION` remains a forward-monitoring hypothesis,
  not an EA rule.

Larger deltas that look favorable only after inspecting holdout are
reported in the CSV but are not accepted. Selecting them would leak the
holdout into policy design.

## Decision Rule

Do not modify BrokerReplay unless a frozen policy adds trades on holdout
while maintaining the agreed non-inferiority margin. Small samples must be
treated as inconclusive even when observed precision is high.

## Outputs

- `/home/cmake/Vectorcodex/VECTOR80/generated/VECTOR80_MARKET_MAP_THRESHOLD_STUDY.csv`
- `/home/cmake/Vectorcodex/VECTOR80/generated/VECTOR80_MARKET_MAP_THRESHOLD_CANDIDATES.csv`
- `/home/cmake/Vectorcodex/VECTOR80/generated/VECTOR80_MARKET_MAP_THRESHOLD_STUDY.md`
