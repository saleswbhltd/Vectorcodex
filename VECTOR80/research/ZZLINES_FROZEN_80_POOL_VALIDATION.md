# ZZLines Frozen 80% Pool Validation

This validation freezes the discovered group definitions and thresholds. No new group or threshold search is performed.

## OOS Pool Result

- OOS window: `2026-03-01` to `2026-06-01 23:55:00`
- Raw signal rows before dedupe: `50`
- Deduped signal rows: `34`
- Hits: `28`
- Precision: `82.4%`
- Same-side cooldown: `30` minutes
- BUY: `25` signals, `20` hits, `80.0%` precision
- SELL: `9` signals, `8` hits, `88.9%` precision

## Monthly Stability

- `2026-03`: `12` signals, `11` hits, `91.7%` precision
- `2026-04`: `12` signals, `10` hits, `83.3%` precision
- `2026-05`: `9` signals, `6` hits, `66.7%` precision
- `2026-06`: `1` signals, `1` hits, `100.0%` precision

## Engine Rows

- `BUY_LL_HGB_088`: raw `15` / `13` (86.7%), deduped `10` / `9`, AUC `0.798`
- `BUY_LL_HIGHVOL_RF_085`: raw `15` / `13` (86.7%), deduped `7` / `5`, AUC `0.903`
- `SELL_HH_BULLCONT_LONDON_HGB_096`: raw `5` / `5` (100.0%), deduped `5` / `5`, AUC `0.985`
- `BUY_LL_BEARCONT_ASIAN_RF_070`: raw `5` / `4` (80.0%), deduped `4` / `3`, AUC `0.913`
- `BUY_HL_HGB_090`: raw `5` / `4` (80.0%), deduped `4` / `3`, AUC `0.839`
- `SELL_HH_HGB_090`: raw `5` / `4` (80.0%), deduped `4` / `3`, AUC `0.813`

## Readiness Decision

- Status: `READY_FOR_EA_PROTOTYPE`
- Meaning: ready to code as a model-backed EA prototype and validate on broker feature export.

## Outputs

- `/home/cmake/Vector/research/zzlines_frozen_80_pool_oos_signals.csv`
- `/home/cmake/Vector/research/zzlines_frozen_80_pool_monthly.csv`
- `/home/cmake/Vector/research/zzlines_frozen_80_pool_group_validation.csv`