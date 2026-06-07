# EURUSD Broker-Adjusted M5 Feature Archive

## Purpose

This dataset adapts Dukascopy tick-derived M5 microstructure features to the
RoboForex ECN feature domain. It supports MARKET_MAP and strategy research when
genuine historical broker ticks are unavailable.

It is not a synthetic or reconstructed RoboForex tick feed.

## Output

| Year | M5 Rows | First Bar UTC | Last Bar UTC |
|---|---:|---|---|
| 2023 | 74,640 | 2023-01-01 22:00 | 2023-12-29 21:55 |
| 2024 | 74,972 | 2024-01-01 22:00 | 2024-12-31 21:55 |

Files:

- `EURUSD_M5_broker_adjusted_2023.csv.gz`
- `EURUSD_M5_broker_adjusted_2024.csv.gz`
- `BROKER_ADJUSTED_MANIFEST.json`

## Data Contract

Dukascopy fields, not adjusted:

- UTC bar timestamp;
- midpoint open, high, low and close;
- summed quoted bid and ask volume.

RoboForex-calibrated M5 features:

- tick count;
- median and maximum tick interval;
- average and maximum spread;
- bid and ask aggressor percentage;
- aggressor imbalance;
- first-half and second-half tick velocity;
- second-to-first-half velocity ratio;
- maximum intrabar run up and run down;
- percentage of ticks near the high and low.

Each calibrated feature also has a `*_duka` column preserving its original
Dukascopy value.

## Validation

- Duplicate M5 timestamps: `0` in both years.
- All 15 canonical calibrated fields were produced in both files.
- Mapped values remain inside the target calibration support.
- Missing values are confined to velocity features where a bar has too few
  usable ticks or a zero first-half denominator.
- Raw yearly tick archives remain unchanged.

Selected annual means show the effect of calibration:

| Year | Feature | Dukascopy | Broker-adjusted |
|---|---|---:|---:|
| 2023 | tick count | 369.047 | 364.179 |
| 2023 | average spread, pips | 0.434 | 0.242 |
| 2023 | median tick interval, ms | 3149.620 | 1785.416 |
| 2024 | tick count | 275.932 | 270.457 |
| 2024 | average spread, pips | 0.311 | 0.125 |
| 2024 | median tick interval, ms | 918.844 | 1857.905 |

The annual mapped means are not expected to equal the calibration sample means.
Quantile mapping transforms each observed feature value; it does not force a
different historical year's marginal distribution to match the later sample.

## Limitation

The calibration was estimated from synchronized Dukascopy and RoboForex data
from December 2025 and April-June 2026. Applying it to 2023-2024 assumes the
relationship between providers is stable through time. Results must therefore
be treated as calibrated proxy features, not direct broker observations.

## Reproduction

```bash
cd /home/cmake/Vectorcodex/VECTOR80
python3 scripts/build_broker_adjusted_tick_features.py --years 2023 2024
python3 -m unittest tests.test_broker_adjusted_features -v
```
