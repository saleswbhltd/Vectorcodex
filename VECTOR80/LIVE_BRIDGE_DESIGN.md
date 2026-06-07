# VECTOR80 Live Bridge

## Runtime contract

- MT5 appends every EURUSD tick to a daily `VECTOR80_LIVE_TICKS_*.csv` file.
- MT5 refreshes `VECTOR80_mt5_heartbeat.csv` every second.
- On each new M5 bar, the EA writes score requests for the completed M5 bar.
- Python checks for a changed request file every two seconds and keeps the frozen models loaded in memory.
- Each request is persisted as handled before feature work starts and is never retried.
- The frozen model bundle is cached on disk; normal startup does not retrain models.
- Python writes `VECTOR80_model_scores_live.csv` atomically.
- Python refreshes `VECTOR80_bridge_heartbeat.csv` every two seconds.
- The EA waits up to 30 seconds for the requested scores.
- Missing, stale, starting, or failed bridge state blocks new trades.
- Demo heuristic fallback remains disabled in the live preset.

## Automatic startup

Run `windows\Install-VECTOR80BridgeTask.ps1` once from Windows PowerShell.
The scheduled supervisor starts at Windows logon, waits for `terminal64.exe`,
starts the bridge through WSL, and restarts it five seconds after any failure.

## Alerts

- MT5 shows an `Alert()` and optionally sends an MT5 push notification.
- Alerts are rate-limited to avoid repeated messages.
- Bridge state and errors are also written to `VECTOR80_bridge.log`.

## Frequencies

- Tick transport: every broker tick.
- MT5 heartbeat: 1 second.
- Python heartbeat: 5 seconds.
- Python request-file check: 2 seconds.
- Bridge considered stale: 15 seconds.
- Score wait deadline: 30 seconds.
- Supervisor restart delay: 5 seconds.
- Python is restricted to CPU cores 0-1 and low process priority.

## Additional safeguards

- Fail closed: no heartbeat or no exact score means no new position.
- Atomic score-file replacement prevents partial CSV reads.
- Exact bar-time and engine-ID matching; live tolerance should be zero.
- Completed-bar scoring avoids changing intrabar features.
- Daily tick files limit corruption and simplify recovery.
- Keep at least 14 days of ticks for H1 and slow-indicator warm-up.
- Reject duplicate requests and duplicate score rows.
- Retain logs for MT5, bridge, requests, scores, and trades.
- Add a daily startup self-test before trading: tick freshness, model load,
  request/response round trip, account ID, symbol, timeframe, and spread.
- Add hard daily loss, maximum consecutive-loss, and maximum order-size guards.
- Use a VPS or prevent Windows sleep while unattended demo trading is active.
