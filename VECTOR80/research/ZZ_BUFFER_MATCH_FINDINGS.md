# ZigZag Lines MTF Buffer Match Findings

Date: 2026-06-02

Source indicator settings from `zz m5.set`:

- `Depth=12`
- `Deviation=5`
- `Backstep=3`
- `ind_period=0`
- `tmp_max_bars=1000`

## Export

`VECTOR_ZZBufferPivotExport.mq5` was compiled with MetaEditor and run from MT5.

Main export files:

- `Common/Files/VECTOR_ZZBUF_EURUSD_PERIOD_M5_D12_Dev5_Back3_Tmp1000_raw.csv`
- `Common/Files/VECTOR_ZZBUF_EURUSD_PERIOD_M5_D12_Dev5_Back3_Tmp1000_parsed_pivots.csv`

The raw buffer export contains 20,000 M5 bars:

- `2026-02-25 02:05:00` to `2026-06-02 22:25:00`

## Buffer Behavior

The indicator's buffers `5/6` are rolling support/resistance levels in this export, not sparse confirmed pivot points.

The usable current ZigZag tip data is:

- `b0`: tip price
- `b1`: tip time as Unix timestamp
- `b4`: leg direction, `+1` high leg / `-1` low leg

Parsed `b0/b1/b4` indicator pivots:

- total: 70
- label counts: `H0=1`, `HH=20`, `LH=14`, `L0=1`, `HL=14`, `LL=20`

Broker OHLC depth-12 pivots over the same 20,000 bars:

- total: 788
- label counts: `H0=1`, `HH=172`, `LH=221`, `L0=1`, `HL=193`, `LL=200`

Exact indicator-vs-broker-OHLC matches:

- exact time + price + side + label: 31
- side-only exact time: 39

## Dukascopy Match

Important correction: broker indicator buffer timestamps are broker/server time. They must be shifted `-3h` to align with Dukascopy UTC data.

Dukascopy panel currently overlaps the shifted indicator export only:

- `2026-05-28 11:25:00` to `2026-06-01 23:55:00`

Without the `-3h` shift, the match looked poor. With the `-3h` shift:

- broker indicator pivots: 54
- Dukascopy depth-12 pivots: 36
- exact matches by time + price + side + label: 12

Nearest-time same-side match:

- 0 minutes: 30 matches
- 5 minutes: 33 matches
- 30 minutes: 34 matches
- 60 minutes: 34 matches

Nearest-time same-side plus label match:

- 0 minutes: 25 matches
- 5 minutes: 28 matches
- 30 minutes: 29 matches
- 60 minutes: 31 matches

Same-side price error:

- within 5 minutes: 33 matches, mean absolute error 0.07 pips
- within 60 minutes: 39 matches, mean absolute error 0.39 pips

## Decision

The `-3h` broker-to-UTC shift makes the Market indicator buffer pivots match Dukascopy well on price and side for the overlapping window. The previous no-shift conclusion was wrong.

Remaining constraint: one MT5 buffer export only returned the current/recent 70 indicator pivots, not a full 20,000-bar pivot history. To extend to a whole year, we need either a rolling MT5 exporter that samples the indicator through historical windows or a verified Python reproduction of the indicator logic using the shifted broker/Dukascopy bars.
