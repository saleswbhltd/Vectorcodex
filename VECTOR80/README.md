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
| `scripts/generate_vector80_full_scores.py` | Leakage-safe generator for every M5 bar and all eight engines in an OOS period |
| `scripts/generate_vector80_broker_scores.py` | All-bar scorer for a fresh broker tick export |
| `scripts/vector80_live_bridge.py` | Persistent request/response scoring bridge with heartbeat |
| `windows/Install-VECTOR80BridgeTask.ps1` | One-time Windows scheduled-task installer |
| `LIVE_BRIDGE_DESIGN.md` | Live pipeline contract, frequencies, alerts, and safeguards |
| `presets/VECTOR80_BrokerReplay_FullCoverage.set` | MT5 validation preset using the full OOS score file with demo fallback disabled |
| `presets/VECTOR80_BrokerReplay_DemoAllBars.set` | Demo preset using refreshed Python broker scores with no heuristic fallback |
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
- scores every M5 bar for all eight engines from `2026-03-01` through
  `2026-06-01 23:55`;
- writes CSV timestamps in UTC research time; the EA automatically derives the
  broker offset with no time-shift input required;
- writes the MT5 score file separately from diagnostics.

Copy `generated/VECTOR80_model_scores_full_oos.csv` to MT5
`Terminal\Common\Files`, load
`presets/VECTOR80_BrokerReplay_FullCoverage.set`, and rerun EURUSD M5 with real
ticks over the same OOS period. Do not enable demo exploration or heuristic
fallback for this comparison.

## Demo All-Bar Scores

Compile and run `VECTOR80_BrokerTickExport_Current.mq5`. Its default
`InpTo=0` exports through the current broker time. Then run:

```bash
cd /home/cmake/Vectorcodex/VECTOR80
python3 scripts/generate_vector80_broker_scores.py
```

Copy `generated/VECTOR80_model_scores_broker_all_bars.csv` to MT5
`Terminal\Common\Files`, then load
`presets/VECTOR80_BrokerReplay_DemoAllBars.set` on EURUSD M5. This preset keeps
validated engine thresholds, disables heuristic fallback, uses `0.1%` risk,
and limits the EA to two open positions.

## Live Demo Bridge

The live preset now uses `VECTOR80_model_scores_live.csv`, requires a fresh
Python heartbeat, disables heuristic fallback, and uses exact score timestamps.
Install automatic bridge supervision once from Windows PowerShell:

```powershell
& "\\wsl.localhost\Ubuntu\home\cmake\Vectorcodex\VECTOR80\windows\Install-VECTOR80BridgeTask.ps1"
```

Compile the updated `ea\VECTOR80_BrokerReplay.mq5`, copy the live preset into
the terminal Presets folder, and load it on EURUSD M5. See
`LIVE_BRIDGE_DESIGN.md` for the runtime contract and failure behavior.

## Adaptive UTC Threshold Rule

`VECTOR80_BrokerReplay` includes an adjustable threshold rule based on the
time-zone study:

- active window: `00:00-02:00 UTC`;
- threshold reduction: `0.08`;
- minimum allowed score: `0.70`;
- stops, targets, engine routing and cooldowns remain unchanged.

Set `InpAdaptiveAllowEntries=false` to stop adaptive trades while retaining
shadow-candidate logging. Set `InpAdaptiveTimeRuleEnabled=false` to remove the
time rule completely. `InpAdaptiveStartUtcMinutes`,
`InpAdaptiveEndUtcMinutes`, `InpAdaptiveThresholdDelta` and
`InpAdaptiveMinScore` are adjustable inputs.

`VECTOR80_live_adaptive_thresholds.csv` records all candidates within
`InpAdaptiveResearchMaxDelta` of their validated threshold throughout the day,
not only candidates inside the active window. Each candidate receives a
`TARGET`, `STOP` or `TIMEOUT` outcome using the same engine stop, target and
timeout. The row also records UTC slot, score gap and MARKET_MAP state, allowing
later threshold optimization without changing the live rule during collection.

Analyze completed outcomes with:

```bash
python3 VECTOR80/scripts/analyze_vector80_adaptive_log.py \
  /path/to/VECTOR80_live_adaptive_thresholds.csv --rule-window-only
```

The report scans candidate threshold deltas and groups results by UTC slot and
engine. It requires 30 completed outcomes by default before labeling a result
eligible for recommendation, and ranks eligible deltas by the 95% Wilson lower
confidence bound rather than raw win rate.

## Automatic Time HUD

`include/VECTOR_TIME/VectorTime.mqh` provides a reusable `CVectorTime` service.
It measures the live MT5 trade-server offset against UTC and rechecks it every
30 seconds. VECTOR80 uses that detected offset for the adaptive UTC rule and
for MARKET_MAP's live heatmap/time-of-day lookup. Strategy Tester and historical
studies retain date-aware broker DST conversion for reproducible old bars.
If automatic synchronization is unavailable, stale or inconsistent, VECTOR80
blocks new entries, displays a red `VECTOR TIME ERROR - CHECK EA` warning and
sends an alert/notification. Trading resumes automatically after time health
recovers.

The chart HUD displays UTC, broker and computer-local clocks, plus Tokyo,
London and New York clocks. London and New York daylight-saving changes are
calculated from their regional calendars. Each market line shows either the
remaining time until its local `17:00` session end or until its next opening
(Tokyo `09:00`, London/New York `08:00`).

Use `InpTimeHudEnabled` to show or hide it. Position, font size and color are
also EA inputs.

## MARKET_MAP

`include/MARKET_MAP/MarketMap.mqh` is a reusable, non-trading market-state
analyzer. It exposes direction, structure, volatility phase, transition,
strength, liquidity, exhaustion and supporting diagnostics from completed M5
bars.

```cpp
#include <MARKET_MAP/MarketMap.mqh>

CMarketMap map;
MarketMapState state;

map.Init(_Symbol, PERIOD_M5, MM_MODE_NATIVE);
map.Update();
if(map.GetState(state))
   Print(MarketMapDirectionName(state.direction), " ",
         MarketMapStructureName(state.structure), " ",
         MarketMapRegimeName(state.regime));
```

The observer dashboard is `indicators/MARKET_MAP_Dashboard.mq5`. Version 0.2
uses native MT5 prices and indicators plus historical volatility context. It
does not alter VECTOR80 trades. Forecast structures are retained for a future
validated provider but are explicitly unavailable in version 0.2. See
`docs/MARKET_MAP_SPEC.md` for the state, forecast, time and data contracts.

`ea/MARKET_MAP_Test.mq5` is the non-trading Strategy Tester harness. It records
every completed M5 state to CSV and demonstrates a conservative trend-filter
integration for other EAs.

Research timestamps are UTC. RoboForex server timestamps are converted using
exact `Europe/Helsinki` EET/EEST rules and broker/Dukascopy alignment must pass
before model training.

The completed indicator, forecast, trend and regime studies are indexed in
`docs/MARKET_MAP_RESEARCH_INDEX.md`. Their durable snapshot is stored under
`/home/cmake/VectorShared/research/MARKET_MAP`, available from Windows as
`\\wsl.localhost\Ubuntu\home\cmake\VectorShared\research\MARKET_MAP`.

The historical day/time visualization is
`generated/EURUSD_MARKET_MAP_HEATMAPS.html`. It contains direction, structure,
volatility, strength and cross-map overlap views using calibrated UTC history.

`generated/EURUSD_MARKET_MAP_HISTORICAL_ZONES_2023_2025.html` combines the same
Historical Zones maps for 2023, 2024 and 2025 at 15-minute and 5-minute
resolution.

`generated/EURUSD_MARKET_MAP_TRADABILITY.html` adds 15-minute volume,
liquidity, spread, path-cleanliness and strategy-fit zones, validated against
March-June 2026 with 30-minute parent confirmation.

`generated/MARKET_MAP_TRADABILITY_2024Q4_VALIDATION.md` independently checks
the frozen zones against October-December 2024 broker-adjusted history.

`generated/MARKET_MAP_TREND_TERMINATION_2024Q4.md` tests whether current
strength, volatility, time and microstructure predict continuation versus
retracement for deduplicated active-movement episodes.

`generated/EURUSD_MARKET_MAP_TRADABILITY_2023_2024.html` compares independent
full-year maps and visualizes changes in zone quality and strategy fit.
The standalone `EURUSD_MARKET_MAP_TRADABILITY_2023.html` and
`EURUSD_MARKET_MAP_TRADABILITY_2024.html` files use the original five-layer
2025 map renderer.

The Dukascopy EURUSD tick archive now includes complete calendar-year files for
2023 and 2024. See `docs/DUKASCOPY_TICK_ARCHIVE.md` for paths, checksums,
coverage, schema, broker-adjusted M5 features and reproduction commands.
