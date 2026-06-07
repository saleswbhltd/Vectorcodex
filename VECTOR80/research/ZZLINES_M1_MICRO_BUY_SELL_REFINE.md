# ZZLines M1 Micro BUY/SELL Refinement

Target: BUY = HL+LL, SELL = HH+LH; offsets `[0, 1, 2]`, stop `12` pips, `1.5R`, horizon `120` minutes.

Adds M1 path/rejection features inside each M5 entry bar.

## Best OOS Precision

- BUY: `MISS`, model `hgb`, mode `all_bars`, threshold `0.80`, signals `61`, hits `16`, precision `26.2%`, recall `9.6%`, AUC `0.801`
- SELL: `MISS`, model `rf`, mode `all_bars`, threshold `0.75`, signals `5`, hits `2`, precision `40.0%`, recall `1.3%`, AUC `0.794`

## Outputs

- `/home/cmake/Vector/research/zzlines_m1_micro_buy_sell_quality.csv`
- `/home/cmake/Vector/research/zzlines_m1_micro_buy_sell_oos_signals.csv`