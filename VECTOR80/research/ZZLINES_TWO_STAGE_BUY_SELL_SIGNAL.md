# ZZLines Two-Stage BUY/SELL Signal

Target: BUY = HL+LL, SELL = HH+LH; offsets `[0, 1, 2]`, stop `12` pips, `1.5R`, horizon `120` minutes.

Stage A predicts pivot timing. Stage B predicts trade quality on true pivot-entry bars.

## Best OOS Precision

- BUY: `MISS`, quality model `q_hgb`, score `timing`, mode `all_bars`, threshold `0.94`, signals `7`, hits `2`, precision `28.6%`, recall `1.2%`, trade AUC `0.799`
- SELL: `MISS`, quality model `q_rf`, score `min_score`, mode `all_bars`, threshold `0.75`, signals `7`, hits `4`, precision `57.1%`, recall `2.5%`, trade AUC `0.810`

## Outputs

- `/home/cmake/Vector/research/zzlines_two_stage_buy_sell_quality.csv`
- `/home/cmake/Vector/research/zzlines_two_stage_buy_sell_oos_signals.csv`