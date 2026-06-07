# TKTL003 / ZZLEG001 Depth Pivot Compare

Depth: `12` M5 bars each side

Confirmed historical pivots are rebuilt from OHLC because TKTL003 marks the indicator's confirmed buffers as unreliable in Strategy Tester.

## Bar overlap

- Broker M5 bars: `24,243` from `2025-02-02 22:00:00` to `2025-05-30 20:50:00`
- Dukascopy M5 bars: `24,243` from `2025-02-02 22:00:00` to `2025-05-30 20:50:00`

## Pivot counts

- Broker pivots: `949` {'H0': 1, 'HH': 233, 'LH': 241, 'L0': 1, 'HL': 256, 'LL': 217}
- Dukascopy pivots: `949` {'H0': 1, 'HH': 234, 'LH': 240, 'L0': 1, 'HL': 257, 'LL': 216}
- Exact matches by time + price + side + label: `144`
- Broker only exact rows: `805`
- Dukascopy only exact rows: `805`

## Nearest-time matches

| match_mode | tolerance_minutes | matches | broker_recall | duka_recall |
|---|---:|---:|---:|---:|
| side | 0 | 444 | 0.468 | 0.468 |
| side | 5 | 450 | 0.474 | 0.474 |
| side | 10 | 456 | 0.481 | 0.481 |
| side | 15 | 461 | 0.486 | 0.486 |
| side | 30 | 477 | 0.503 | 0.503 |
| side | 60 | 820 | 0.864 | 0.864 |
| side+label | 0 | 416 | 0.438 | 0.438 |
| side+label | 5 | 422 | 0.445 | 0.445 |
| side+label | 10 | 426 | 0.449 | 0.449 |
| side+label | 15 | 430 | 0.453 | 0.453 |
| side+label | 30 | 440 | 0.464 | 0.464 |
| side+label | 60 | 787 | 0.829 | 0.829 |

## Price error for same-side pivots within 5 minutes

- Matched pivots: `450`
- Mean absolute price error: `0.17` pips
- Median absolute price error: `0.10` pips
- 95th percentile absolute price error: `0.70` pips
