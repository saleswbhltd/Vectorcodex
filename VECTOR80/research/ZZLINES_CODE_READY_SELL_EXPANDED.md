# VECTOR80 SELL-Expanded Code-Ready Engine Set

This keeps the accepted BUY engines and expands SELL from 5 to 21 OOS signals.

## Validation

- Signals: `42`
- Hits: `36`
- Precision: `85.7%`
- Monthly minimum precision for months with >=3 signals: `75.0%`

## Side Split

- `BUY`: `21` signals, `17` hits, `81.0%`
- `SELL`: `21` signals, `19` hits, `90.5%`

## Monthly

- `2026-03`: `13` signals, `12` hits, `92.3%`
- `2026-04`: `19` signals, `16` hits, `84.2%`
- `2026-05`: `8` signals, `6` hits, `75.0%`
- `2026-06`: `2` signals, `2` hits, `100.0%`

## SELL Engines

- `SELL_label_session_vol_HH_LONDON_HIGH_rf_075`: group `HH|LONDON|HIGH`, model `RandomForestClassifier`, threshold `0.75`, OOS `4` signals, `4` hits, `100.0%`
- `SELL_label_HH_hgb_09`: group `HH`, model `HistGradientBoostingClassifier`, threshold `0.9`, OOS `7` signals, `6` hits, `85.7%`
- `SELL_label_trade_context_session_HH_BULL_CONTINUATION_HIGH_LONDON_hgb_096`: group `HH|BULL_CONTINUATION_HIGH|LONDON`, model `HistGradientBoostingClassifier`, threshold `0.96`, OOS `6` signals, `5` hits, `83.3%`
- `SELL_label_trade_context_session_vol_HH_BULL_CONTINUATION_HIGH_LONDON_HIGH_rf_07`: group `HH|BULL_CONTINUATION_HIGH|LONDON|HIGH`, model `RandomForestClassifier`, threshold `0.7`, OOS `2` signals, `2` hits, `100.0%`
- `SELL_label_trade_context_HH_BEAR_TREND_BREAK_HIGH_extra_07`: group `HH|BEAR_TREND_BREAK_HIGH`, model `ExtraTreesClassifier`, threshold `0.7`, OOS `2` signals, `2` hits, `100.0%`

## Decision

- Status: `SELL_EXPANSION_READY_FOR_EA_PROTOTYPE`
- SELL signal count increased from `5` to `21` while SELL precision stayed above `90%`.

## Outputs

- `/home/cmake/Vector/research/vector80_sell_expanded_engine_config.json`
- `/home/cmake/Vector/research/zzlines_code_ready_sell_expanded_oos_signals.csv`
- `/home/cmake/Vector/research/zzlines_code_ready_sell_expanded_monthly.csv`