# VECTOR80 Codex Project

This folder is the Codex-owned VECTOR80 EA workspace.

## Ownership Split

- `/home/cmake/Vector` remains the Claude-run project for `VECTOR001`, `VECTOR002`, and `VECTOR003`.
- `/home/cmake/Vectorcodex/VECTOR80` is the Codex-run project for the `VECTOR80` series.
- Shared research, tick-history artifacts, Python research scripts, model files, and notes live under `/home/cmake/VectorShared` and are linked through `../shared`.

## Active Files

| Path | Purpose |
|---|---|
| `ea/VECTOR80_BrokerReplay.mq5` | Active VECTOR80 EA source for broker replay/backtest work |
| `ea/VECTOR80_Prototype.mq5` | Earlier VECTOR80 prototype source |
| `mt5_scripts/VECTOR80_BrokerTickExport_Current.mq5` | MT5 script to export fresh broker ticks for score refresh |
| `scripts/refresh_vector80_scores.py` | Python scorer that refreshes `VECTOR80_model_scores.csv` from exported ticks and EA missing-score events |
| `scripts/generate_vector80_full_scores.py` | Leakage-safe generator for every eligible M5 engine/bar in an OOS period |
| `presets/VECTOR80_BrokerReplay_FullCoverage.set` | MT5 validation preset using the full OOS score file with demo fallback disabled |
| `generated/VECTOR80_model_scores_full_oos.csv` | Generated March 1-June 1, 2026 score coverage for MT5 |
| `generated/FULL_COVERAGE_VALIDATION.md` | Generation checks, counts, and exact Strategy Tester rerun procedure |
| `research` | Symlink to `/home/cmake/VectorShared/research` |
| `models` | Symlink to `/home/cmake/VectorShared/models` |
| `notes/close-up/2026-06-03_2045.md` | Close-up handoff that identified `VECTOR80_BrokerReplay` as the active EA |

## Notes

The original `VECTOR80_*.mq5` files in `/home/cmake/Vector` were copied here, not removed. Treat this folder as the canonical Codex working copy going forward.

## Option 1: Refresh CSV Scores

The current EA uses `SCORE_EXTERNAL_CSV`. It will not trade live/demo pivots unless `Common\Files\VECTOR80_model_scores.csv` contains matching score rows.

Run this flow:

1. In MetaTrader 5, compile and run the script:

   ```text
   Scripts\VECTOR80_BrokerTickExport_Current.mq5
   ```

   It is installed at:

   ```text
   C:\Users\cmake\AppData\Roaming\MetaQuotes\Terminal\F1138FAFA5BD40AC6E39B58188E4EE88\MQL5\Scripts\VECTOR80_BrokerTickExport_Current.mq5
   ```

   Default export window:

   ```text
   2026.06.01 00:00 -> 2026.06.05 00:00
   ```

   Expected output:

   ```text
   C:\Users\cmake\AppData\Roaming\MetaQuotes\Terminal\Common\Files\VECTOR80_BROKER_TICKS_EURUSD_20260601_20260605.csv
   ```

2. After the export exists, run:

   ```bash
   cd /home/cmake/Vectorcodex/VECTOR80
   ./scripts/refresh_vector80_scores.py \
     --ticks /mnt/c/Users/cmake/AppData/Roaming/MetaQuotes/Terminal/Common/Files/VECTOR80_BROKER_TICKS_EURUSD_20260601_20260605.csv \
     --day 2026-06-04
   ```

The scorer retrains the frozen VECTOR80 engine definitions from the historical research panel, scores the EA's `missing_external_score` candidates from `VECTOR80_events.csv`, and writes:

```text
/home/cmake/VectorShared/research/VECTOR80_model_scores.csv
C:\Users\cmake\AppData\Roaming\MetaQuotes\Terminal\Common\Files\VECTOR80_model_scores.csv
```

It does not fabricate scores. If tick data or required feature rows are missing, it stops with an error instead of writing unsafe rows.

## Full OOS Score Coverage

The original March-May Strategy Tester report used a sparse CSV containing only
42 historical score rows. Generate broad, leakage-safe coverage with:

```bash
cd /home/cmake/Vectorcodex/VECTOR80
python3 scripts/generate_vector80_full_scores.py
```

The generator:

- trains all eight engines only on `2025-06-02` through `2026-02-28`;
- uses training-period medians for missing-feature imputation;
- scores every stage-1 eligible M5 bar from `2026-03-01` through
  `2026-06-01 23:55`;
- writes CSV timestamps in research time, leaving the EA to apply
  `InpScoreTimeShiftMin=180`;
- writes the MT5 score file separately from diagnostics.

Copy `generated/VECTOR80_model_scores_full_oos.csv` to MT5
`Terminal\Common\Files`, load
`presets/VECTOR80_BrokerReplay_FullCoverage.set`, and rerun EURUSD M5 with real
ticks over the same OOS period. Do not enable demo exploration or heuristic
fallback for this comparison.
