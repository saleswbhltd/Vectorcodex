# ZZLines Pivot Classification Redo

All numbers use the validated ZigZag Lines MTF Python map, not the old 20-pip threshold map.

## Pivot Counts

- DEV pivots: `3181` {'HH': 794, 'HL': 813, 'LH': 797, 'LL': 777}
- OOS pivots: `1140` {'HH': 272, 'HL': 288, 'LH': 298, 'LL': 282}

## Stage 1 Greedy Cover

- HH: rules `1`, recall `97.7%`, fire `26.4%`, exact precision `4.60%`
- LL: rules `1`, recall `96.4%`, fire `23.8%`, exact precision `5.00%`
- HL: rules `2`, recall `93.2%`, fire `33.3%`, exact precision `2.29%`
- LH: rules `2`, recall `93.0%`, fire `34.2%`, exact precision `2.25%`

## Stage 2 Best OOS Precision With >=10 Signals

- HH: threshold `0.80`, signals `92`, hits `48`, precision `52.2%`, recall `7.4%`, AUC `0.764`
- HL: threshold `0.80`, signals `86`, hits `36`, precision `41.9%`, recall `6.6%`, AUC `0.814`
- LH: threshold `0.80`, signals `117`, hits `37`, precision `31.6%`, recall `6.6%`, AUC `0.756`
- LL: threshold `0.80`, signals `130`, hits `55`, precision `42.3%`, recall `8.2%`, AUC `0.767`

## Outputs

- `/home/cmake/Vector/research/zzlines_pivot_map_enriched.csv`
- `/home/cmake/Vector/research/zzlines_indicator_scan.csv`
- `/home/cmake/Vector/research/zzlines_indicator_kept.csv`
- `/home/cmake/Vector/research/zzlines_detection_matrix.csv`
- `/home/cmake/Vector/research/zzlines_detection_matrix_top.md`
- `/home/cmake/Vector/research/zzlines_greedy_cover_summary.csv`
- `/home/cmake/Vector/research/zzlines_greedy_cover_rules.md`
- `/home/cmake/Vector/research/zzlines_stage2_candidate_quality.csv`
- `/home/cmake/Vector/research/ZZLINES_STAGE2_CANDIDATE_QUALITY.md`