# MARKET_MAP Indicator Family Study

Balanced logistic models are fitted through December 31, 2025 and tested
from March 1 through June 1, 2026. Moves within 1 pip are excluded.

## Overall AUC

| Family | 5m | 10m | 15m | 30m | 60m |
|---|---:|---:|---:|---:|---:|
| H1_CONTEXT | 0.497 | 0.503 | 0.505 | 0.512 | 0.513 |
| M5_MOMENTUM | 0.532 | 0.530 | 0.526 | 0.532 | 0.527 |
| MICROSTRUCTURE | 0.511 | 0.507 | 0.506 | 0.509 | 0.503 |
| VOLATILITY | 0.506 | 0.495 | 0.496 | 0.494 | 0.486 |
| H1_PLUS_M5 | 0.532 | 0.532 | 0.527 | 0.535 | 0.527 |
| H1_PLUS_MICRO | 0.504 | 0.509 | 0.509 | 0.516 | 0.518 |

## Best Segments

### 5 minutes

| Family | Segment | Rows | AUC |
|---|---|---:|---:|
| H1_PLUS_M5 | SESSION:NEW_YORK | 1,582 | 0.550 |
| M5_MOMENTUM | SESSION:LONDON_NY | 2,380 | 0.549 |
| H1_PLUS_M5 | SESSION:LONDON_NY | 2,380 | 0.549 |
| M5_MOMENTUM | SESSION:NEW_YORK | 1,582 | 0.549 |
| H1_PLUS_M5 | VOL_BUCKET:NORMAL | 2,180 | 0.540 |
| M5_MOMENTUM | VOL_BUCKET:NORMAL | 2,180 | 0.540 |
| M5_MOMENTUM | VOL_BUCKET:LOW | 2,166 | 0.532 |
| H1_PLUS_M5 | VOL_BUCKET:HIGH | 4,326 | 0.531 |
| H1_PLUS_M5 | VOL_BUCKET:LOW | 2,166 | 0.529 |
| M5_MOMENTUM | VOL_BUCKET:HIGH | 4,326 | 0.528 |

### 10 minutes

| Family | Segment | Rows | AUC |
|---|---|---:|---:|
| M5_MOMENTUM | SESSION:NEW_YORK | 2,091 | 0.551 |
| H1_PLUS_M5 | SESSION:NEW_YORK | 2,091 | 0.549 |
| H1_PLUS_MICRO | SESSION:LATE | 655 | 0.541 |
| M5_MOMENTUM | SESSION:LONDON_NY | 2,838 | 0.541 |
| H1_PLUS_M5 | SESSION:LONDON_NY | 2,838 | 0.541 |
| MICROSTRUCTURE | SESSION:LATE | 655 | 0.539 |
| M5_MOMENTUM | VOL_BUCKET:LOW | 3,134 | 0.535 |
| H1_PLUS_M5 | VOL_BUCKET:LOW | 3,134 | 0.534 |
| H1_PLUS_M5 | VOL_BUCKET:NORMAL | 2,782 | 0.533 |
| H1_PLUS_M5 | VOL_BUCKET:HIGH | 5,147 | 0.531 |

### 15 minutes

| Family | Segment | Rows | AUC |
|---|---|---:|---:|
| M5_MOMENTUM | SESSION:NEW_YORK | 2,363 | 0.552 |
| H1_PLUS_M5 | SESSION:NEW_YORK | 2,363 | 0.551 |
| H1_PLUS_M5 | SESSION:LONDON_NY | 3,008 | 0.547 |
| M5_MOMENTUM | SESSION:LONDON_NY | 3,008 | 0.546 |
| H1_PLUS_M5 | VOL_BUCKET:NORMAL | 3,106 | 0.530 |
| H1_PLUS_M5 | VOL_BUCKET:HIGH | 5,543 | 0.529 |
| H1_CONTEXT | SESSION:LATE | 755 | 0.528 |
| M5_MOMENTUM | VOL_BUCKET:NORMAL | 3,106 | 0.528 |
| M5_MOMENTUM | VOL_BUCKET:HIGH | 5,543 | 0.527 |
| H1_CONTEXT | SESSION:ASIAN | 3,329 | 0.527 |

### 30 minutes

| Family | Segment | Rows | AUC |
|---|---|---:|---:|
| M5_MOMENTUM | SESSION:NEW_YORK | 2,714 | 0.567 |
| H1_PLUS_M5 | SESSION:NEW_YORK | 2,714 | 0.560 |
| H1_PLUS_M5 | SESSION:LONDON_NY | 3,318 | 0.558 |
| M5_MOMENTUM | SESSION:LONDON_NY | 3,318 | 0.556 |
| H1_CONTEXT | SESSION:ASIAN | 3,908 | 0.539 |
| H1_PLUS_M5 | VOL_BUCKET:NORMAL | 3,564 | 0.538 |
| H1_PLUS_M5 | VOL_BUCKET:HIGH | 6,063 | 0.538 |
| M5_MOMENTUM | VOL_BUCKET:NORMAL | 3,564 | 0.535 |
| H1_PLUS_MICRO | SESSION:ASIAN | 3,908 | 0.535 |
| M5_MOMENTUM | VOL_BUCKET:LOW | 4,452 | 0.533 |

### 60 minutes

| Family | Segment | Rows | AUC |
|---|---|---:|---:|
| M5_MOMENTUM | SESSION:NEW_YORK | 2,978 | 0.559 |
| H1_PLUS_MICRO | SESSION:LATE | 1,193 | 0.555 |
| H1_CONTEXT | SESSION:LATE | 1,193 | 0.552 |
| H1_PLUS_M5 | SESSION:LATE | 1,193 | 0.546 |
| H1_CONTEXT | SESSION:ASIAN | 4,454 | 0.546 |
| H1_PLUS_M5 | SESSION:LONDON_NY | 3,486 | 0.544 |
| H1_PLUS_M5 | VOL_BUCKET:HIGH | 6,428 | 0.544 |
| H1_PLUS_MICRO | SESSION:ASIAN | 4,454 | 0.543 |
| MICROSTRUCTURE | SESSION:NEW_YORK | 2,978 | 0.542 |
| H1_PLUS_MICRO | VOL_BUCKET:HIGH | 6,428 | 0.534 |

## Gate

- A family needs overall AUC >= 0.55 and no major session collapse before further work.
- Segment results are diagnostic and must not be used to create time filters without a second OOS period.
- Models remain disconnected from live trading.
