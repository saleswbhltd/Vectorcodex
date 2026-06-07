# VECTOR80 Code-Ready Engine Set

This is the frozen engine subset selected for EA prototyping.

## Validation

- OOS window: `2026-03-01` to `2026-06-01 23:55:00`
- Signals: `26`
- Hits: `22`
- Precision: `84.6%`
- Monthly minimum precision for months with >=3 signals: `80.0%`

## Monthly

- `2026-03`: `9` signals, `8` hits, `88.9%`
- `2026-04`: `11` signals, `9` hits, `81.8%`
- `2026-05`: `5` signals, `4` hits, `80.0%`
- `2026-06`: `1` signals, `1` hits, `100.0%`

## Side Split

- `BUY`: `21` signals, `17` hits, `81.0%`
- `SELL`: `5` signals, `5` hits, `100.0%`

## Engines

- `BUY_LL_HGB_088`: side `BUY`, group `LL`, model `HistGradientBoostingClassifier`, threshold `0.88`, risk `5p/1.0R/120m`, OOS `10` signals, `9` hits, `90.0%`
- `BUY_LL_HIGHVOL_RF_085`: side `BUY`, group `LL|HIGH`, model `RandomForestClassifier`, threshold `0.85`, risk `5p/1.0R/120m`, OOS `7` signals, `5` hits, `71.4%`
- `SELL_HH_BULLCONT_LONDON_HGB_096`: side `SELL`, group `HH|BULL_CONTINUATION_HIGH|LONDON`, model `HistGradientBoostingClassifier`, threshold `0.96`, risk `8p/1.0R/120m`, OOS `5` signals, `5` hits, `100.0%`
- `BUY_HL_HGB_090`: side `BUY`, group `HL`, model `HistGradientBoostingClassifier`, threshold `0.9`, risk `5p/1.0R/120m`, OOS `4` signals, `3` hits, `75.0%`

## EA Coding Notes

- Use one signal router with a `30` minute same-side cooldown.
- Trade BUY engines with `5` pip stop and `1R` target.
- Trade SELL engines with `8` pip stop and `1R` target.
- Entry is allowed on the pivot bar close, `+1`, or `+2` M5 bars.
- Keep `HH/HL/LH/LL`, session, volatility regime, and trade context in the log row.
- Before live trading, export the same feature columns from MT5 broker data and verify model parity.

## Outputs

- `/home/cmake/Vector/research/vector80_engine_config.json`
- `/home/cmake/Vector/research/zzlines_code_ready_oos_signals.csv`
- `/home/cmake/Vector/research/zzlines_code_ready_monthly.csv`