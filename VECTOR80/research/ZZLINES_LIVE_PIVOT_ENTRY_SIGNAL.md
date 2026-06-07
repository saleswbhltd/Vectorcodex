# ZZLines Live Pivot Entry Signal

Target: entry offsets `[0, 1, 2]`, stop `12` pips beyond pivot, `1.5R`, horizon `120` minutes.

This test uses Stage 1 candidate bars first, then filters candidates with a per-class model.
`all_bars` counts every qualifying bar. `first_cross` keeps the first threshold crossing. `run_peak` keeps the highest-score bar in each threshold run. Event modes use a `6` bar cooldown.

## Best OOS Precision With >=10 Signals

- HH: mode `all_bars`, threshold `0.80`, signals `50`, hits `10`, precision `20.0%`, recall `12.7%`, AUC `0.707`
- HL: mode `all_bars`, threshold `0.90`, signals `11`, hits `3`, precision `27.3%`, recall `6.5%`, AUC `0.868`
- LH: mode `run_peak`, threshold `0.70`, signals `110`, hits `6`, precision `5.5%`, recall `10.5%`, AUC `0.777`
- LL: mode `run_peak`, threshold `0.80`, signals `23`, hits `8`, precision `34.8%`, recall `7.4%`, AUC `0.734`

## Interpretation

- The perfect-pivot entry test is not enough for EA deployment; live candidates are far more imbalanced.
- `all_bars` can overstate practical signal quality because adjacent bars from the same setup are counted separately.
- Event-style signals show LL is the strongest class so far. HH is marginal. HL and LH need better timing/proximity features before EA rules should use them.
- The next research step should split the live problem into pivot-timing detection first, then trade-quality filtering second.

## Outputs

- `/home/cmake/Vector/research/zzlines_live_pivot_entry_signal_quality.csv`
- `/home/cmake/Vector/research/zzlines_live_pivot_entry_oos_signals.csv`