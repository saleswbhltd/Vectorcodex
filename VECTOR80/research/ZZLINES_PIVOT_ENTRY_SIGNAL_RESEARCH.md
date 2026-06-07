# ZZLines Pivot Entry Signal Research

Entry is tested at pivot bar close, +1 bar close, and +2 bar close.
Conservative same-bar conflict rule: stop wins before target.

## Best Raw Entry Outcomes

### HH

| offset | stop | R | horizon | target% | stop% | median MFE | median MAE | median R |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | 5 | 1.0 | 120m | 82.2% | 4.3% | 14.0 | 2.0 | 1.85 |
| 0 | 5 | 1.0 | 60m | 72.1% | 1.6% | 11.0 | 1.0 | 1.43 |
| 0 | 8 | 1.0 | 120m | 65.7% | 5.6% | 14.0 | 2.0 | 1.35 |
| 0 | 5 | 1.5 | 120m | 61.3% | 9.6% | 14.0 | 2.0 | 1.85 |
| 1 | 5 | 1.0 | 120m | 61.3% | 9.4% | 12.0 | 4.0 | 1.24 |
| 0 | 8 | 1.0 | 60m | 51.3% | 1.1% | 11.0 | 1.0 | 1.01 |
| 2 | 5 | 1.0 | 120m | 50.1% | 12.6% | 11.0 | 4.0 | 1.01 |
| 0 | 12 | 1.0 | 120m | 48.2% | 4.4% | 14.0 | 2.0 | 0.98 |

### HL

| offset | stop | R | horizon | target% | stop% | median MFE | median MAE | median R |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | 5 | 1.0 | 120m | 77.9% | 7.7% | 12.0 | 2.0 | 1.72 |
| 0 | 5 | 1.0 | 60m | 66.6% | 2.0% | 10.0 | 1.0 | 1.31 |
| 0 | 8 | 1.0 | 120m | 60.4% | 6.9% | 12.0 | 2.0 | 1.20 |
| 1 | 5 | 1.0 | 120m | 57.1% | 14.0% | 10.0 | 3.0 | 1.15 |
| 0 | 5 | 1.5 | 120m | 57.1% | 12.5% | 12.0 | 2.0 | 1.72 |
| 2 | 5 | 1.0 | 120m | 47.5% | 16.5% | 10.0 | 4.0 | 0.97 |
| 0 | 8 | 1.0 | 60m | 45.4% | 1.8% | 10.0 | 1.0 | 0.93 |
| 1 | 5 | 1.0 | 60m | 42.6% | 4.5% | 8.0 | 2.0 | 0.89 |

### LH

| offset | stop | R | horizon | target% | stop% | median MFE | median MAE | median R |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | 5 | 1.0 | 120m | 77.9% | 5.9% | 12.0 | 2.0 | 1.71 |
| 0 | 5 | 1.0 | 60m | 68.6% | 2.2% | 10.0 | 1.0 | 1.34 |
| 0 | 8 | 1.0 | 120m | 61.1% | 6.3% | 12.0 | 2.0 | 1.20 |
| 1 | 5 | 1.0 | 120m | 58.5% | 11.7% | 11.0 | 3.0 | 1.21 |
| 0 | 5 | 1.5 | 120m | 57.1% | 10.4% | 12.0 | 2.0 | 1.71 |
| 2 | 5 | 1.0 | 120m | 49.0% | 14.1% | 10.0 | 4.0 | 1.00 |
| 0 | 8 | 1.0 | 60m | 46.7% | 1.6% | 10.0 | 1.0 | 0.95 |
| 1 | 5 | 1.0 | 60m | 44.9% | 4.6% | 8.0 | 2.0 | 0.91 |

### LL

| offset | stop | R | horizon | target% | stop% | median MFE | median MAE | median R |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | 5 | 1.0 | 120m | 81.3% | 4.1% | 14.0 | 2.0 | 1.84 |
| 0 | 5 | 1.0 | 60m | 71.8% | 1.5% | 11.0 | 1.0 | 1.43 |
| 0 | 8 | 1.0 | 120m | 66.6% | 5.2% | 14.0 | 2.0 | 1.32 |
| 0 | 5 | 1.5 | 120m | 63.0% | 8.1% | 14.0 | 2.0 | 1.84 |
| 1 | 5 | 1.0 | 120m | 62.1% | 9.1% | 12.0 | 3.0 | 1.29 |
| 2 | 5 | 1.0 | 120m | 52.3% | 11.1% | 11.0 | 4.0 | 1.05 |
| 0 | 8 | 1.0 | 60m | 51.7% | 1.8% | 11.0 | 1.0 | 1.02 |
| 1 | 8 | 1.0 | 120m | 48.9% | 7.7% | 12.0 | 3.0 | 0.97 |

## Model Quality

Baseline model target: stop `12` pips beyond pivot, `1.5R`, horizon `120` minutes.

Best OOS precision with at least 10 signals:

- HH offset +0: threshold `0.70`, signals `21`, hits `11`, precision `52.4%`, recall `20.8%`, AUC `0.624`
- HH offset +1: threshold `0.70`, signals `21`, hits `5`, precision `23.8%`, recall `19.2%`, AUC `0.581`
- HH offset +2: threshold `0.60`, signals `19`, hits `5`, precision `26.3%`, recall `23.8%`, AUC `0.645`
- HL offset +0: threshold `0.60`, signals `44`, hits `18`, precision `40.9%`, recall `34.0%`, AUC `0.738`
- HL offset +1: threshold `0.50`, signals `51`, hits `15`, precision `29.4%`, recall `41.7%`, AUC `0.680`
- HL offset +2: threshold `0.40`, signals `61`, hits `11`, precision `18.0%`, recall `40.7%`, AUC `0.670`
- LH offset +0: threshold `0.70`, signals `19`, hits `16`, precision `84.2%`, recall `25.0%`, AUC `0.779`
- LH offset +1: threshold `0.60`, signals `49`, hits `16`, precision `32.7%`, recall `42.1%`, AUC `0.683`
- LH offset +2: threshold `0.50`, signals `40`, hits `13`, precision `32.5%`, recall `38.2%`, AUC `0.704`
- LL offset +0: threshold `0.70`, signals `18`, hits `14`, precision `77.8%`, recall `19.2%`, AUC `0.751`
- LL offset +1: threshold `0.50`, signals `58`, hits `12`, precision `20.7%`, recall `31.6%`, AUC `0.641`
- LL offset +2: threshold `0.60`, signals `27`, hits `7`, precision `25.9%`, recall `25.0%`, AUC `0.624`

## Outputs

- `/home/cmake/Vector/research/zzlines_pivot_entry_outcomes.csv`
- `/home/cmake/Vector/research/zzlines_pivot_entry_summary.csv`
- `/home/cmake/Vector/research/zzlines_pivot_entry_model_quality.csv`