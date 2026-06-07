# ZZLines Tradable Pivot Group Mining

Practical tradable definition:
- BUY pivots: stop `5`, target `1R`, horizon `120m`.
- SELL pivots: stop `8`, target `1R`, horizon `120m`.

## Tradable Pivot Count

- Total real pivots: `6,077`
- Practical tradable pivots: `4,516`
- Tradable rate: `74.3%`

## Top Groups By Tradable Pivots

- `side:BUY` total `3038`, tradable `2500`, OOS tradable `455`
- `side:SELL` total `3039`, tradable `2016`, OOS tradable `357`
- `label:LL` total `1473`, tradable `1253`, OOS tradable `237`
- `role:BUY|SWING` total `1473`, tradable `1253`, OOS tradable `237`
- `label:HL` total `1565`, tradable `1247`, OOS tradable `218`
- `role:BUY|PULLBACK` total `1565`, tradable `1247`, OOS tradable `218`
- `trend:BUY|TREND_ALIGNED` total `1182`, tradable `1008`, OOS tradable `197`
- `label:HH` total `1503`, tradable `1035`, OOS tradable `181`
- `role:SELL|SWING` total `1503`, tradable `1035`, OOS tradable `181`
- `label:LH` total `1536`, tradable `981`, OOS tradable `176`
- `role:SELL|PULLBACK` total `1536`, tradable `981`, OOS tradable `176`
- `trade_context:RANGE` total `1448`, tradable `1037`, OOS tradable `166`

## Detection Results

- No tested group reached `80%+` OOS precision with at least `10` live signals.

### Best Per Group

- `label:LL` best `78.6%`, signals `14`, hits `11`, AUC `0.800`
- `role:BUY|SWING` best `78.6%`, signals `14`, hits `11`, AUC `0.800`
- `trade_context:RANGE` best `73.3%`, signals `15`, hits `11`, AUC `0.930`
- `label:HH` best `70.0%`, signals `20`, hits `14`, AUC `0.812`
- `role:SELL|SWING` best `70.0%`, signals `20`, hits `14`, AUC `0.812`
- `label_trade_context:HH|BEAR_TREND_BREAK_HIGH` best `68.8%`, signals `16`, hits `11`, AUC `0.838`
- `side_trade_context:SELL|BEAR_TREND_BREAK_HIGH` best `68.8%`, signals `16`, hits `11`, AUC `0.838`
- `trade_context:BEAR_TREND_BREAK_HIGH` best `68.8%`, signals `16`, hits `11`, AUC `0.838`
- `side:SELL` best `66.7%`, signals `30`, hits `20`, AUC `0.796`
- `side:BUY` best `66.7%`, signals `12`, hits `8`, AUC `0.816`
- `trend:SELL|COUNTER_TREND` best `63.6%`, signals `11`, hits `7`, AUC `0.843`
- `label_trade_context:LL|BEAR_CONTINUATION_LOW` best `61.1%`, signals `18`, hits `11`, AUC `0.913`
- `side_trade_context:BUY|BEAR_CONTINUATION_LOW` best `61.1%`, signals `18`, hits `11`, AUC `0.913`
- `trade_context:BEAR_CONTINUATION_LOW` best `61.1%`, signals `18`, hits `11`, AUC `0.913`
- `trend:SELL|TREND_ALIGNED` best `60.0%`, signals `10`, hits `6`, AUC `0.804`
- `label:HL` best `53.3%`, signals `15`, hits `8`, AUC `0.841`
- `role:BUY|PULLBACK` best `53.3%`, signals `15`, hits `8`, AUC `0.841`
- `label_trade_context:HH|BULL_CONTINUATION_HIGH` best `50.0%`, signals `10`, hits `5`, AUC `0.853`
- `side_trade_context:SELL|BULL_CONTINUATION_HIGH` best `50.0%`, signals `10`, hits `5`, AUC `0.853`
- `trade_context:BULL_CONTINUATION_HIGH` best `50.0%`, signals `10`, hits `5`, AUC `0.853`
- `label_trade_context:HL|BUY_PULLBACK_UPTREND` best `46.2%`, signals `13`, hits `6`, AUC `0.932`
- `side_trade_context:BUY|BUY_PULLBACK_UPTREND` best `46.2%`, signals `13`, hits `6`, AUC `0.932`
- `trade_context:BUY_PULLBACK_UPTREND` best `46.2%`, signals `13`, hits `6`, AUC `0.932`
- `label_trade_context:LL|BULL_TREND_BREAK_LOW` best `45.5%`, signals `22`, hits `10`, AUC `0.919`
- `side_trade_context:BUY|BULL_TREND_BREAK_LOW` best `45.5%`, signals `22`, hits `10`, AUC `0.919`

## Outputs

- `/home/cmake/Vector/research/zzlines_tradable_pivot_catalog.csv`
- `/home/cmake/Vector/research/zzlines_tradable_pivot_groups.csv`
- `/home/cmake/Vector/research/zzlines_tradable_group_detection_quality.csv`
- `/home/cmake/Vector/research/zzlines_tradable_group_oos_signals.csv`