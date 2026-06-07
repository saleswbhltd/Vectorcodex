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

