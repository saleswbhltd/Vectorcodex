# VECTOR80 logging runbook

## Active terminal

Vector80 is expected to run on portable RoboF2 only:

- Terminal root: `C:\Users\cmake\MT5\RoboF2`
- EA source: `C:\Users\cmake\MT5\RoboF2\MQL5\Experts\Advisors\VECTOR80_BrokerReplay.mq5`
- EA binary: `C:\Users\cmake\MT5\RoboF2\MQL5\Experts\Advisors\VECTOR80_BrokerReplay.ex5`

## Primary Vector80 logs

Use these first for signal/trade reconstruction:

- Events: `C:\Users\cmake\MT5\RoboF2\MQL5\Files\VECTOR80\LIVE\VECTOR80_events.csv`
- Trades: `C:\Users\cmake\MT5\RoboF2\MQL5\Files\VECTOR80\LIVE\VECTOR80_trades.csv`
- Adaptive thresholds: `C:\Users\cmake\MT5\RoboF2\MQL5\Files\VECTOR80\LIVE\VECTOR80_adaptive_thresholds.csv`
- Tick captures: `C:\Users\cmake\MT5\RoboF2\MQL5\Files\VECTOR80\LIVE\VECTOR80_LIVE_TICKS_GBPUSD_YYYYMMDD.csv`

`VECTOR80_events.csv` contains signals, blocks, order failures, debug summaries, and raw `TRADE_TRANSACTION` rows.

`VECTOR80_trades.csv` contains `OPEN`, `TIMEOUT_CLOSE`, and from this build forward `DEAL_CLOSE` rows for broker close deals. `DEAL_CLOSE` is the row to use for SL/TP close result, pips, position ticket, engine id, and close comment.

## MT5 platform logs

Use these if the Vector files disagree with broker execution:

- Experts log: `C:\Users\cmake\MT5\RoboF2\MQL5\Logs\YYYYMMDD.log`
- Terminal/broker log: `C:\Users\cmake\MT5\RoboF2\Logs\YYYYMMDD.log`

Expected Expert log messages:

- `VECTOR80 LOG OK` confirms event/trade CSV handles opened.
- `VECTOR80 LOG ERROR` means the EA could not open or write the Vector CSV files.
- `VECTOR80 EVENT SIGNAL` shows the exact signal, score, threshold, liquidity label, distance, and rejection state.
- `VECTOR80 ORDER_SUBMIT` shows order intent before broker execution.
- `VECTOR80 ORDER_RESULT ok/fail` shows broker result for the submitted order.
- `VECTOR80 TRADE_TRANSACTION` shows every MT5 trade transaction for the symbol.
- `VECTOR80 TRADE OPEN` and `VECTOR80 TRADE DEAL_CLOSE` mirror rows written to `VECTOR80_trades.csv`.

## Chart screenshots

Trade screenshots are stored separately by ChartCamera:

- `C:\Users\cmake\MT5\RoboF2\MQL5\Files\ChartCamera\LIVE\67196088\GBPUSD_P5`

Use screenshots only for visual context. Do not use them as the primary trade ledger now that `DEAL_CLOSE` is logged to `VECTOR80_trades.csv`.

## 6E liquidity data

The EA reads 6E profile data from:

- `C:\Users\cmake\MT5\RoboF2\MQL5\Files\6E_profile_levels.csv`
- `C:\Users\cmake\MT5\RoboF2\MQL5\Files\6E_volume_profile.csv`

If stale, missing, or malformed, Vector80 logs warnings/blocks in `VECTOR80_events.csv` and the Experts log.

## Quick PowerShell checks

```powershell
$base = 'C:\Users\cmake\MT5\RoboF2'
Get-ChildItem "$base\MQL5\Files\VECTOR80\LIVE" | Sort-Object LastWriteTime -Descending | Select-Object Name,LastWriteTime,Length
Import-Csv "$base\MQL5\Files\VECTOR80\LIVE\VECTOR80_events.csv" | Select-Object -Last 20
Import-Csv "$base\MQL5\Files\VECTOR80\LIVE\VECTOR80_trades.csv" | Select-Object -Last 20
Select-String -Path "$base\MQL5\Logs\$(Get-Date -Format yyyyMMdd).log" -Pattern 'VECTOR80 LOG|VECTOR80 EVENT|VECTOR80 TRADE|ORDER_RESULT|TRADE_TRANSACTION'
```
