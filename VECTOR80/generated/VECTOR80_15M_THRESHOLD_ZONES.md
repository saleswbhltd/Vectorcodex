# VECTOR80 15-Minute Threshold-Zone Study

Every one of the 96 UTC quarter-hour slots was tested at threshold
reductions of 0.01, 0.02, 0.03, 0.05, 0.08 and 0.10.

March-April 2026 is discovery. May 1-June 1, 2026 is untouched holdout.
A cell is descriptive unless it has trades in both periods. Testing 576
slot/delta combinations creates substantial multiple-testing risk.

## Repeated Positive Cells

| UTC slot | Delta | Discovery | Holdout | Total |
|---|---:|---:|---:|---:|
| 01:45 | 0.08 | 1/1 | 1/1 | 2/2 |
| 11:15 | 0.10 | 1/1 | 1/1 | 2/2 |

## Discovery Winners That Failed Holdout

| UTC slot | Delta | Discovery | Holdout |
|---|---:|---:|---:|
| 14:15 | 0.10 | 3/3 | 0/3 |
| 14:30 | 0.10 | 2/3 | 0/1 |
| 15:15 | 0.10 | 2/2 | 1/2 |
| 03:45 | 0.10 | 2/2 | 0/1 |
| 19:15 | 0.10 | 2/2 | 0/1 |
| 14:15 | 0.08 | 1/1 | 0/3 |

## Interpretation

- The CSV and HTML show every zone, including no-trade zones.
- A winning cell means more than half of its added candidates hit the
  existing VECTOR80 target definition; it does not prove future edge.
- Prefer cells positive in both discovery and holdout, with several
  independent trades. Do not enable isolated 1/1 cells.
- The exact 15-minute scan is a diagnostic map. Neighboring-slot and
  forward accumulation are required before changing the EA.

## Outputs

- `/home/cmake/Vectorcodex/VECTOR80/generated/VECTOR80_15M_THRESHOLD_ZONES.csv`
- `/home/cmake/Vectorcodex/VECTOR80/generated/VECTOR80_15M_THRESHOLD_ZONE_SUMMARY.csv`
- `/home/cmake/Vectorcodex/VECTOR80/generated/EURUSD_VECTOR80_15M_THRESHOLD_ZONES.html`
- `/home/cmake/Vectorcodex/VECTOR80/generated/VECTOR80_15M_THRESHOLD_ZONES.md`
