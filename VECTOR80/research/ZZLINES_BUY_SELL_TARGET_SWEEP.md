# ZZLines BUY/SELL Target Sweep

This checks whether 80% OOS precision is reachable by changing stop/R/horizon target definition.

## Best OOS Precision With >=5 Signals

- BUY: `PASS`, stop `5`, R `1.0`, horizon `120m`, mode `all_bars`, threshold `0.92`, signals `7`, hits `6`, precision `85.7%`, recall `0.9%`, AUC `0.810`
- SELL: `MISS`, stop `8`, R `1.0`, horizon `120m`, mode `all_bars`, threshold `0.88`, signals `14`, hits `11`, precision `78.6%`, recall `2.2%`, AUC `0.811`

## Output

- `/home/cmake/Vector/research/zzlines_buy_sell_target_sweep_quality.csv`