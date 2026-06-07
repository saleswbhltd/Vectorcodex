# ZZLines SELL Expansion Mining

Passing SELL candidate rows after dedupe: `26` signals, `23` hits, `88.5%` precision.

## Candidate Groups

- `label:HH` labels `HH` model `hgb` mode `first_cross` threshold `0.90` signals `11` hits `9` precision `81.8%`
- `label:HH` labels `HH` model `hgb` mode `run_peak` threshold `0.90` signals `11` hits `9` precision `81.8%`
- `label_trade_context:HH|BEAR_TREND_BREAK_HIGH` labels `HH` model `extra` mode `all_bars` threshold `0.70` signals `8` hits `7` precision `87.5%`
- `label_session_vol:HH|LONDON|HIGH` labels `HH` model `rf` mode `run_peak` threshold `0.75` signals `7` hits `6` precision `85.7%`
- `label_trade_context:HH|BEAR_TREND_BREAK_HIGH` labels `HH` model `extra` mode `first_cross` threshold `0.70` signals `6` hits `5` precision `83.3%`
- `label_trade_context:HH|BEAR_TREND_BREAK_HIGH` labels `HH` model `extra` mode `run_peak` threshold `0.70` signals `6` hits `5` precision `83.3%`
- `label_trade_context_session:HH|BULL_CONTINUATION_HIGH|LONDON` labels `HH` model `hgb` mode `all_bars` threshold `0.96` signals `6` hits `5` precision `83.3%`
- `label_trade_context_session:HH|BULL_CONTINUATION_HIGH|LONDON` labels `HH` model `hgb` mode `first_cross` threshold `0.96` signals `6` hits `5` precision `83.3%`
- `label_trade_context_session:HH|BULL_CONTINUATION_HIGH|LONDON` labels `HH` model `hgb` mode `run_peak` threshold `0.96` signals `6` hits `5` precision `83.3%`
- `label_vol:HH|HIGH` labels `HH` model `hgb` mode `all_bars` threshold `0.94` signals `5` hits `4` precision `80.0%`
- `label_vol:HH|HIGH` labels `HH` model `hgb` mode `first_cross` threshold `0.94` signals `5` hits `4` precision `80.0%`
- `label_vol:HH|HIGH` labels `HH` model `hgb` mode `run_peak` threshold `0.94` signals `5` hits `4` precision `80.0%`
- `label:HH` labels `HH` model `hgb` mode `all_bars` threshold `0.92` signals `3` hits `3` precision `100.0%`
- `label:HH` labels `HH` model `hgb` mode `first_cross` threshold `0.92` signals `3` hits `3` precision `100.0%`
- `label:HH` labels `HH` model `hgb` mode `run_peak` threshold `0.92` signals `3` hits `3` precision `100.0%`
- `label_trade_context_session_vol:HH|BULL_CONTINUATION_HIGH|LONDON|HIGH` labels `HH` model `rf` mode `all_bars` threshold `0.70` signals `3` hits `3` precision `100.0%`
- `label_trade_context_session_vol:HH|BULL_CONTINUATION_HIGH|LONDON|HIGH` labels `HH` model `rf` mode `first_cross` threshold `0.70` signals `3` hits `3` precision `100.0%`
- `label_trade_context_session_vol:HH|BULL_CONTINUATION_HIGH|LONDON|HIGH` labels `HH` model `rf` mode `run_peak` threshold `0.70` signals `3` hits `3` precision `100.0%`

## Outputs

- `/home/cmake/Vector/research/zzlines_sell_expansion_quality.csv`
- `/home/cmake/Vector/research/zzlines_sell_expansion_candidate_signals.csv`