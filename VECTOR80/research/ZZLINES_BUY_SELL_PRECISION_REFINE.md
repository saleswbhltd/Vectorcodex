# ZZLines BUY/SELL Precision Refinement

Target: BUY = HL+LL, SELL = HH+LH; offsets `[0, 1, 2]`, stop `12` pips, `1.5R`, horizon `120` minutes.

Methods: causal support/resistance features, temporal deltas/lags, HGB, RandomForest, ExtraTrees.

## Best OOS Precision

- BUY: `MISS`, model `hgb`, mode `first_cross`, threshold `0.88`, signals `5`, hits `2`, precision `40.0%`, recall `1.2%`, AUC `0.788`
- SELL: `MISS`, model `hgb`, mode `run_peak`, threshold `0.85`, signals `11`, hits `6`, precision `54.5%`, recall `3.8%`, AUC `0.792`

## Notes

- `all_bars` is useful for ranking but can count repeated bars in the same setup.
- `first_cross` and `run_peak` are closer to EA event behavior.
- SR features are causal: current bars only see earlier ZZLines levels.

## Outputs

- `/home/cmake/Vector/research/zzlines_buy_sell_precision_refine_quality.csv`
- `/home/cmake/Vector/research/zzlines_buy_sell_precision_refine_oos_signals.csv`