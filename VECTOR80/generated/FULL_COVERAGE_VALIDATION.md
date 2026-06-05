# VECTOR80 Full Coverage Validation

Generated on 2026-06-05 for the OOS period:

```text
2026-03-01 00:00:00 through 2026-06-01 23:55:00
```

Training remains frozen at:

```text
2025-06-02 00:00:00 through 2026-02-28 23:59:59
```

## Output Checks

- Engine/bar score rows: `152,328`
- Unique M5 bars: `19,041`
- Engines scored per bar: `8`
- Rows at or above engine threshold: `80`
- Original historical score keys: `42`
- Original keys present in the full file: `42`
- Duplicate `time + engine_id` rows: `0`
- Original keys still above threshold after deterministic retraining: `35`

The score CSV contains broad model output. A score row is not a trade by itself.
The EA must still detect a new ZigZag pivot, match the engine group, pass its
threshold, pass cooldown and spread checks, and satisfy position limits.

## MT5 Deployment

Copy:

```text
generated/VECTOR80_model_scores_full_oos.csv
```

to:

```text
C:\Users\cmake\AppData\Roaming\MetaQuotes\Terminal\Common\Files\VECTOR80_model_scores_full_oos.csv
```

Copy or load:

```text
presets/VECTOR80_BrokerReplay_FullCoverage.set
```

from the active terminal's:

```text
MQL5\Profiles\Tester
```

Run:

```text
Expert: VECTOR80_BrokerReplay
Symbol: EURUSD
Period: M5
Dates: 2026.03.01 through 2026.06.01
Model: Every tick based on real ticks
Initial deposit: 3000
```

The preset keeps:

```text
InpScoreMode=0
InpScoreTimeShiftMin=180
InpScoreTimeToleranceMin=5
InpDemoExploreMode=false
InpDemoExploreFallbackHeuristic=false
InpRiskPct=0.1
InpMaxOpenPositions=4
```

Save the next Strategy Tester report as HTML. Compare total trades, net profit,
profit factor, drawdown, long/short win rates, and monthly trade distribution
against `ReportTester-67196088.html`.
