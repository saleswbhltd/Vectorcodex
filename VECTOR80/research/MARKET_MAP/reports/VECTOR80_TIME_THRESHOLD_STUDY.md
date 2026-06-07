# VECTOR80 Time-Conditioned Threshold Study

## Question

Can VECTOR80 thresholds be lowered during specific UTC clock windows, such
as early morning or late afternoon, to add trades without losing quality?

## Design

- Published VECTOR80 signals and model thresholds remain the baseline.
- Clock is UTC. RoboForex broker time is UTC+2 in winter and UTC+3 in summer.
- Discovery: March 1-April 30, 2026.
- Holdout: May 1-June 1, 2026.
- Threshold reductions: 0.01, 0.02, 0.03, 0.05, 0.08 and 0.10.
- Tested predefined windows, two-hour bins and day-of-week/four-hour bins.
- Same-side additions within 30 minutes of baseline or another addition are
  removed.
- Discovery gate: at least 5 additions, at least 75% added precision and
  combined precision within 3 percentage points of baseline.

Below-threshold candidates examined: `512`.

## Baseline

- DISCOVERY: `32` signals, `28` hits, `87.5%` precision.
- HOLDOUT: `10` signals, `8` hits, `80.0%` precision.

## Discovery

`2` settings passed; top frozen settings:

| UTC window | Delta | Added | Added precision | Combined precision | Increase |
|---|---:|---:|---:|---:|---:|
| UTC_00_02 | 0.08 | 5 | 80.0% | 86.5% | 15.6% |
| EARLY_ASIA_00_04 | 0.08 | 8 | 75.0% | 85.0% | 25.0% |

## Holdout

| UTC window | Delta | Added | Added precision | Combined precision | Increase |
|---|---:|---:|---:|---:|---:|
| EARLY_ASIA_00_04 | 0.08 | 6 | 50.0% | 68.8% | 60.0% |
| UTC_00_02 | 0.08 | 3 | 100.0% | 84.6% | 30.0% |

## Conclusion

- `UTC_00_02` with a `0.08` threshold reduction is the only narrow
  clock window that passed discovery and repeated in holdout.
- It added 5 discovery trades at 80% and 3 holdout trades at 100%.
  The total is only 8 additions, so this is not sufficient for live
  activation after testing many candidate windows.
- Late afternoon did not qualify. In holdout, `16:00-20:00 UTC` with
  a `0.05` reduction added 5 trades but only 1 hit.
- Keep current thresholds live. Forward-monitor `00:00-02:00 UTC`
  as a shadow rule until a larger independent sample is collected.

Any window that looks good only in holdout is not accepted because that
would use the holdout to choose the rule.

## Outputs

- `/home/cmake/Vectorcodex/VECTOR80/generated/VECTOR80_TIME_THRESHOLD_STUDY.csv`
- `/home/cmake/Vectorcodex/VECTOR80/generated/VECTOR80_TIME_THRESHOLD_CANDIDATES.csv`
- `/home/cmake/Vectorcodex/VECTOR80/generated/VECTOR80_TIME_THRESHOLD_SELECTED_ADDITIONS.csv`
- `/home/cmake/Vectorcodex/VECTOR80/generated/VECTOR80_TIME_THRESHOLD_STUDY.md`
