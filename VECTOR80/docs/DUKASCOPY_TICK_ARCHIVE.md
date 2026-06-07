# Dukascopy EURUSD Tick Archive

## Coverage

The historical tick archive is split into complete calendar-year files:

| Year | Rows | First Tick UTC | Last Tick UTC | Compressed Size |
|---|---:|---|---|---:|
| 2023 | 27,545,689 | 2023-01-01 22:04:01.067 | 2023-12-29 21:59:59.385 | 249 MB |
| 2024 | 20,687,149 | 2024-01-01 22:00:12.108 | 2024-12-31 21:59:58.249 | 186 MB |

The first and last timestamps reflect actual market availability. Weekend and
holiday closures are not filled with synthetic ticks.

Existing later history:

`/home/cmake/VectorShared/research/EURUSD_TICK_dukascopy_2025_2026.csv.gz`

It begins at `2025-01-01 22:00:14.647 UTC` and continues through
`2026-06-01 23:59:57.653 UTC`.

## Files

Directory:

`/home/cmake/VectorShared/research/dukascopy/EURUSD/2023_2024`

Windows/WSL:

`\\wsl.localhost\Ubuntu\home\cmake\VectorShared\research\dukascopy\EURUSD\2023_2024`

Year files:

- `EURUSD_TICK_dukascopy_2023.csv.gz`
- `EURUSD_TICK_dukascopy_2024.csv.gz`

Manifest:

- `EURUSD_TICK_20230101_20250101_exclusive.manifest.json`

The hidden `.parts` directory contains validated monthly compressed partitions
for resumable recovery. Do not delete it until all derived M1/M5 datasets have
been built and verified.

## Broker-Adjusted M5 Features

Derived yearly files are stored in:

`/home/cmake/VectorShared/research/dukascopy/EURUSD/2023_2024/broker_adjusted`

- `EURUSD_M5_broker_adjusted_2023.csv.gz`
- `EURUSD_M5_broker_adjusted_2024.csv.gz`
- `BROKER_ADJUSTED_MANIFEST.json`
- `BROKER_ADJUSTED_2023_2024_REPORT.md`

These are not reconstructed RoboForex ticks. Their M5 midpoint OHLC and quoted
bid/ask volumes remain Dukascopy data. Fifteen M5 microstructure features are
quantile-mapped to the RoboForex ECN feature distribution using
`tick_calibration.json`; the original value is retained in a matching
`*_duka` column.

The calibration was learned from overlapping December 2025 and April-June 2026
data and projected backward. Research using these files therefore assumes that
the provider relationship was stable in 2023-2024.

## Schema

```text
datetime,bid,ask,bid_vol,ask_vol,mid
```

Timestamps are UTC. `mid = (bid + ask) / 2`.

## Validation

- Total new ticks: `48,232,838`.
- Download error hours after retry: `0`.
- Duplicate timestamps: `0`.
- Non-monotonic timestamps: `0`.
- Quotes with ask below bid: `0`.
- Rows outside their calendar year: `0`.
- Both gzip streams pass integrity testing.
- Largest gaps are normal weekend market closures.

SHA-256:

```text
f79d88cfd0b333f548f5d55389aa4ef97bb108760fccb174aa782dec72ee59d9  EURUSD_TICK_dukascopy_2023.csv.gz
eb17b2a31f2ea335085bf57aa59fd12becfa0c5b653886a008e5be469128c591  EURUSD_TICK_dukascopy_2024.csv.gz
```

## Reproduction

```bash
cd /home/cmake/Vectorcodex/VECTOR80
python3 scripts/download_dukascopy_ticks.py \
  EURUSD 2023-01-01 2025-01-01 \
  --output-dir /home/cmake/VectorShared/research/dukascopy/EURUSD/2023_2024 \
  --workers 12
```

The end date is exclusive. The downloader saves monthly restart partitions and
then stream-consolidates them into whole-year files.

Build the broker-adjusted M5 feature files:

```bash
python3 scripts/build_broker_adjusted_tick_features.py --years 2023 2024
```
