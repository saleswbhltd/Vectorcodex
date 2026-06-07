# Pivot Research Closeout

Date: 2026-06-02

## Final Source Of Truth

The EA-aligned pivot map is now the Python reproduction of the ZigZag Lines MTF settings:

- `Depth=12`
- `Deviation=5` points
- `Backstep=3`
- `point=0.00001`
- M5 timeframe

Implementation:

- `50_build_zz_lines_mtf_map.py`

This ports the MetaQuotes `Examples\\ZigZag.mq5` algorithm. It is not the earlier 20-pip threshold ZigZag and not the symmetric depth-window pivot scan.

## Validation Result

Validated against the broker MT5 Market-indicator buffer export:

- exported indicator pivots: 70
- Python pivots in same window: 71
- exact time + price + side matches: 70 / 70
- exact time + price + side + label matches: 68 / 70

The two label differences are context effects from validating on a clipped pivot window. The individual pivots match.

Broker indicator times are server time. To compare broker indicator pivots to Dukascopy UTC data, shift broker pivot time by `-3h`.

With the `-3h` shift against Dukascopy:

- overlap broker indicator pivots: 54
- Dukascopy pivots: 36
- exact time + price + side + label matches: 12
- same-side within 5 minutes: 33
- same-side + label within 5 minutes: 28
- mean price error within 5 minutes: 0.07 pips

## Built Maps

One-year Dukascopy map:

- file: `EURUSD_M5_ZZLINES_D12_Dev5_Back3_1Y_FULLDAY_2025-06-02 00:00:00_to_2026-06-01 23:55:00_pivot_map.csv`
- range: `2025-06-02 00:00:00` to `2026-06-01 23:55:00`
- bars: 74,504
- pivots: 4,321
- labels: `H0=1`, `HH=1065`, `LH=1095`, `L0=1`, `HL=1100`, `LL=1059`

Full available Dukascopy map:

- file: `EURUSD_M5_ZZLINES_D12_Dev5_Back3_FULL_AVAILABLE_pivot_map.csv`
- range: `2025-01-01 22:00:00` to `2026-06-01 23:55:00`
- bars: 105,332
- pivots: 6,088
- labels: `H0=1`, `HH=1504`, `LH=1539`, `L0=1`, `HL=1566`, `LL=1477`

## What To Use

Use the one-year ZigZag Lines map for model research and EA-aligned labels.

Use the full available ZigZag Lines map when more training history is useful, but keep walk-forward splits strict.

Do not use `pivot_map.csv` as the main EA label source. That file is the older 20-pip threshold map:

- range: `2025-02-02 23:05:00` to `2026-02-27 14:55:00`
- pivots: 2,006
- labels: `HH=484`, `HL=513`, `LH=519`, `LL=490`

That 20-pip map is a separate research engine and should be fixed or analyzed later as its own issue.

## Finished Decision

Pivot research for the EA-aligned map is complete enough to proceed:

1. The MT5 indicator settings were found and decoded.
2. Buffer behavior was mapped.
3. Broker-vs-UTC time offset was identified as `-3h`.
4. Python reproduction was validated against broker indicator pivots.
5. One-year and full-available pivot maps were generated.

Next work should move from pivot-map construction to signal research on the ZigZag Lines labels.
