# MARKET_MAP Research Model Report

These models are research-only and are not connected to live trading.

| Horizon | Accuracy | Balanced accuracy | Majority baseline | Log loss | Brier |
|---|---:|---:|---:|---:|---:|
| 5m | 0.559 | 0.398 | 0.545 | 0.935 | 0.552 |
| 15m | 0.425 | 0.423 | 0.312 | 1.055 | 0.638 |
| 30m | 0.387 | 0.372 | 0.357 | 1.060 | 0.644 |
| 60m | 0.401 | 0.334 | 0.390 | 1.028 | 0.627 |
| rest_day | 0.473 | 0.338 | 0.446 | 0.893 | 0.569 |

- Features: 76
- Fit rows: 73,955
- Calibration rows: 11,746
- Test rows: 18,950
- Fit period ends 2025-12-31.
- Probability calibration uses January-February 2026.
- Final evaluation starts March 1, 2026.
- This first panel uses an unsupervised tick-domain calibration that includes April-June 2026 broker distributions. No outcome labels were used, but strict production validation must relearn that calibration using pre-test broker data only.

## Deployment Gate

- Keep all models disconnected from live trading.
- Reject every current directional horizon; none exceeds 0.50 balanced accuracy.
- Continue 15m and 30m research because they beat their majority-class baselines,
  but that is not sufficient for deployment.
