# Python ZigZag Lines MTF Replication

Date: 2026-06-02

Implemented in:

- `50_build_zz_lines_mtf_map.py`

Settings:

- `Depth=12`
- `Deviation=5` points
- `Backstep=3`
- point size: `0.00001`

The implementation ports the MetaQuotes `Examples\\ZigZag.mq5` algorithm, not the earlier symmetric depth-window pivot scan.

## Validation

Validated against the exported Market indicator buffer pivots from:

- `VECTOR_ZZBUF_EURUSD_PERIOD_M5_D12_Dev5_Back3_Tmp20000_raw.csv`
- `VECTOR_ZZBUF_EURUSD_PERIOD_M5_D12_Dev5_Back3_Tmp20000_indicator_pivots.csv`

Validation result over the broker indicator window:

- exported indicator pivots: 70
- Python pivots in same window: 71
- exact time + price + side matches: 70 / 70
- exact time + price + side + label matches: 68 / 70

The two label misses come from comparing a clipped validation window, so the previous same-side high/low context starts at a different point.

## One-Year Map

Built on Dukascopy M5 data, UTC:

- range: `2025-06-02 00:00:00` to `2026-06-01 23:55:00`
- bars: 74,504
- pivots: 4,321
- labels: `H0=1`, `HH=1065`, `LH=1095`, `L0=1`, `HL=1100`, `LL=1059`

Output:

- `EURUSD_M5_ZZLINES_D12_Dev5_Back3_1Y_FULLDAY_2025-06-02 00:00:00_to_2026-06-01 23:55:00_pivot_map.csv`

## Full Available Map

Built on all available Dukascopy M5 data:

- range: `2025-01-01 22:00:00` to `2026-06-01 23:55:00`
- bars: 105,332
- pivots: 6,088
- labels: `H0=1`, `HH=1504`, `LH=1539`, `L0=1`, `HL=1566`, `LL=1477`

Output:

- `EURUSD_M5_ZZLINES_D12_Dev5_Back3_FULL_AVAILABLE_pivot_map.csv`

## Time Alignment

Broker indicator timestamps are server time. For matching broker indicator exports to Dukascopy UTC, shift broker indicator pivot times by `-3h`.
