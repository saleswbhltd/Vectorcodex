# MARKET_MAP Trend and Regime Study

The target describes the price path already observed over the trailing 60
minutes. Models use only data available at the current completed M5 bar.
H1 inputs are delayed to the last completed H1 candle.

## Taxonomy

- Direction: `BULL`, `BEAR`, `NEUTRAL`.
- Structure: `TREND`, `CHOP`, `RANGE`.
- Volatility phase: `COMPRESSION`, `NORMAL`, `EXPANSION`.
- Composite regime separates strong/orderly trends, directional chop,
  quiet range and volatile range.

## Continuous Out-of-Sample Classification

| Target | Accuracy | Balanced accuracy | Majority baseline |
|---|---:|---:|---:|
| direction | 0.822 | 0.814 | 0.380 |
| structure | 0.682 | 0.711 | 0.440 |
| volatility | 0.864 | 0.882 | 0.538 |
| regime | 0.566 | 0.610 | 0.226 |

## High-Confidence Accuracy

### direction

| Min probability | Coverage | Rows | Accuracy |
|---|---:|---:|---:|
| 0.350 | 1.000 | 19041 | 0.822 |
| 0.400 | 1.000 | 19041 | 0.822 |
| 0.450 | 0.999 | 19022 | 0.822 |
| 0.500 | 0.989 | 18832 | 0.825 |
| 0.600 | 0.873 | 16619 | 0.863 |
| 0.700 | 0.740 | 14083 | 0.904 |
| 0.800 | 0.590 | 11240 | 0.945 |

### structure

| Min probability | Coverage | Rows | Accuracy |
|---|---:|---:|---:|
| 0.350 | 0.999 | 19029 | 0.682 |
| 0.400 | 0.993 | 18905 | 0.684 |
| 0.450 | 0.973 | 18527 | 0.688 |
| 0.500 | 0.912 | 17364 | 0.700 |
| 0.600 | 0.686 | 13069 | 0.751 |
| 0.700 | 0.473 | 9004 | 0.807 |
| 0.800 | 0.270 | 5132 | 0.880 |

### volatility

| Min probability | Coverage | Rows | Accuracy |
|---|---:|---:|---:|
| 0.350 | 1.000 | 19041 | 0.864 |
| 0.400 | 1.000 | 19038 | 0.864 |
| 0.450 | 0.999 | 19028 | 0.864 |
| 0.500 | 0.997 | 18985 | 0.865 |
| 0.600 | 0.936 | 17824 | 0.886 |
| 0.700 | 0.867 | 16508 | 0.907 |
| 0.800 | 0.783 | 14916 | 0.931 |

### regime

| Min probability | Coverage | Rows | Accuracy |
|---|---:|---:|---:|
| 0.350 | 0.990 | 18844 | 0.568 |
| 0.400 | 0.955 | 18189 | 0.575 |
| 0.450 | 0.876 | 16681 | 0.588 |
| 0.500 | 0.743 | 14155 | 0.606 |
| 0.600 | 0.480 | 9146 | 0.662 |
| 0.700 | 0.281 | 5358 | 0.722 |
| 0.800 | 0.146 | 2772 | 0.790 |

## Composite Regime Distribution

| Regime | All-data share |
|---|---:|
| BULL_CHOP | 0.228 |
| BEAR_CHOP | 0.223 |
| RANGE | 0.149 |
| BULL_TREND | 0.082 |
| BEAR_TREND | 0.080 |
| COMPRESSION | 0.077 |
| STRONG_BULL_TREND | 0.060 |
| STRONG_BEAR_TREND | 0.056 |
| VOLATILE_RANGE | 0.045 |

## Monthly OOS Stability

### direction

| Month | Rows | Accuracy | Balanced accuracy |
|---|---:|---:|---:|
| 2026-03 | 6372 | 0.832 | 0.823 |
| 2026-04 | 6333 | 0.821 | 0.816 |
| 2026-05 | 6048 | 0.812 | 0.804 |
| 2026-06 | 288 | 0.792 | 0.789 |

### structure

| Month | Rows | Accuracy | Balanced accuracy |
|---|---:|---:|---:|
| 2026-03 | 6372 | 0.688 | 0.718 |
| 2026-04 | 6333 | 0.683 | 0.713 |
| 2026-05 | 6048 | 0.674 | 0.701 |
| 2026-06 | 288 | 0.677 | 0.717 |

### volatility

| Month | Rows | Accuracy | Balanced accuracy |
|---|---:|---:|---:|
| 2026-03 | 6372 | 0.865 | 0.882 |
| 2026-04 | 6333 | 0.859 | 0.874 |
| 2026-05 | 6048 | 0.867 | 0.891 |
| 2026-06 | 288 | 0.878 | 0.901 |

### regime

| Month | Rows | Accuracy | Balanced accuracy |
|---|---:|---:|---:|
| 2026-03 | 6372 | 0.571 | 0.615 |
| 2026-04 | 6333 | 0.571 | 0.607 |
| 2026-05 | 6048 | 0.557 | 0.605 |
| 2026-06 | 288 | 0.531 | 0.602 |

## State Duration

| Axis | 5m | 15m | 30m | 60m | Next-hour path agrees |
|---|---:|---:|---:|---:|---:|
| direction | 0.753 | 0.615 | 0.492 | 0.329 | 0.331 |
| structure | 0.636 | 0.487 | 0.397 | 0.345 | 0.348 |
| volatility | 0.920 | 0.826 | 0.711 | 0.540 | 0.410 |
| regime | 0.556 | 0.360 | 0.246 | 0.157 | 0.150 |

## Path Thresholds

- Direction requires a 60-minute net move of at least `0.75 x M5 ATR14`.
- Trend requires at least `1.25 x ATR` net movement and path efficiency >= `0.40`.
- Strong trend requires at least `2.50 x ATR` and efficiency >= `0.55`.
- Compression/expansion compare the trailing 60-minute average M5 range
  with the preceding four-hour baseline.

## Important Limitation

Current-state accuracy and future persistence are different measurements.
A state can be identified correctly now and still change five minutes later.
Accuracy near transitions is expected to be lower than during stable runs.

## Design Recommendation

- Publish direction, structure and volatility as separate state axes.
- Add `TRANSITION` when axis confidence is low or the label recently changed.
- Treat the nine-class composite as a descriptive summary, not the primary truth.
- Recalculate on every completed M5 bar and retain state age/duration.
- A 95% direction state is achievable only selectively: the current study reaches
  94.5% at 59% coverage when model confidence is at least 0.80.
- Structure needs more work; even its high-confidence subset reaches 88.0%.

No model in this study is connected to live trading.
