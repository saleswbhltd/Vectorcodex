---
name: vector003-lessons-learned
description: VECTOR003 implementation failures, root causes, what was fixed, what remains — prevents repeating the same mistakes across sessions
metadata:
  type: project
---

## Tomorrow's priority — the ONE fix that matters

**The core mismatch (attempted 3x, still not fixed):**
- GBM trained on: ZigZag D12/Dev5/Back3 confirmed pivot bars (~12/day)
- EA currently scores: local-3 extreme bars (~800/day, 55% of all M5 bars)
- This 65x universe mismatch is why 62% of trades hit SL even with correct calibration

**What must happen tomorrow:**
Replace local-3 extreme with ZigZag D12/Dev5/Back3 as the entry candidate source in the EA.
The exact same indicator, same settings, same bars the GBM was trained on.
Do NOT use ZZ as a real-time signal trigger (v1.40 mistake) — use it to FILTER which bars get scored.
Approach: on each new M5 bar, check if the last completed bar is within the current ZZ leg's
formation zone (is it at or near the ZZ tip being built?). Only call bridge for those bars.

**Previous attempt failures:**
- v1.40: Used ZZ pivot CONFIRMATION as trigger — fired 12+ bars after pivot formed, missed entry
- v1.30: Local-3 extreme alone — 65x too many bars, GBM misfires constantly
- v1.50 + Stage1: Stage 1 reduced fire rate but still scoring wrong universe

**Do not attempt anything else until this is fixed.**

---

## Core finding: model has real edge but was never correctly deployed

Python OOS backtest (script 81): **+274 pips/month at 1.0p spread, 47.7% WR, 227 trades/month**.
Verified reproducible. The EA implementations failed — not the model.

## Root causes of each EA failure (in order of impact)

### 1. Training data ≠ live data (CRITICAL — calibration in progress)
- GBM trained on Dukascopy tick data (bid_aggressor_pct, spread_avg, velocities etc.)
- EA runs on RoboForex ECN broker — different tick quoting behavior
- OHLC features identical; tick microstructure features differ
- Without tick features, OHLC-only model = -366p/mo (negative)
- Fix: calibrate Dukascopy tick distributions → broker using Dec 2025 + Apr-Jun 2026 overlap
- Scripts: research/84_calibrate_tick_features.py → research/83_broker_rebuild.py
- Broker tick availability: Dec 2025 + Apr-Jun 2026 only (2025-01 to 2025-11 = no data)

### 2. ZigZag indicator: labeling tool ONLY — never a real-time signal
- ZZ D12/Dev5/Back3 labels historical pivot bars (ground truth for training)
- Was NEVER meant as a real-time entry trigger in the EA
- v1.40 mistakenly used ZZ pivot as entry trigger → 33 trades in 35 days (too few)
- Correct: Stage 1 indicator OR-ensemble → Stage 2 GBM → local-3 extreme final gate

### 3. Wrong candidate universe (Stage 1 missing from EA)
- GBM trained on Stage 1 OR-ensemble candidates (~20% of bars, 57–124/day/class)
- EA was scoring ALL local-3 extreme bars (~55% = 13× the training universe)
- Stage 1 thresholds: research/stage1_thresholds.json (8 classes × 3-5 rules each)
- Stage 1 lives in BRIDGE (Python), not EA (MQL5)
- v1.50 correctly gates on Stage 1 in bridge, local-3 as Gate 1 in EA

### 4. Cooldown field name mismatch (fixed v1.20+)
- EA sends: last_buy_signal_unix / last_sell_signal_unix
- Old bridge read: last_signal_time_unix (always None → cooldown bypassed → 2× trades)
- Fixed: bridge reads correct per-direction field names

### 5. bb_pctB hardcoded 0.5 (fixed v1.30+)
- BuildFeaturesJSON sent constant 0.5 placeholder — GBM got useless signal for this feature

### 6. hour_utc = broker time not UTC (fixed v1.30+)
- Research used Dukascopy UTC; broker is UTC+3; feature was 3 hours wrong
- Fixed: bar_broker_time − (TimeCurrent() − TimeGMT())

### 7. 29/70 features missing (fixed v1.30+)
- EA sent 41 features; bridge filled 29 tick features with median (constant/useless)
- Fixed: all 70 features computed including CopyTicksRange tick features

### 8. side/class parsing space bug (fixed v1.20+)
- ParseResponse searched "best_class":"X" but bridge writes "best_class": "X" (space)
- All trades opened as SELL regardless of GBM output
- Fixed: search for key, then scan forward to next quote

### 9. Response file race condition (fixed v1.20+)
- Bridge truncates file before writing → EA reads empty → parse fail 1462/1540 bars
- Fixed: atomic write via os.replace(.tmp)

## Correct pipeline (full spec in VECTOR003_CONTRACT.md)

```
All M5 bars
  → Gate 1: local-3 extreme (EA, ~55% of bars)
  → Gate 2: Stage 1 OR ensemble per class (bridge, stage1_thresholds.json)
  → Stage 2: 8 GBMs → best_class + best_prob
  → Gate 3: prob ≥ 0.70 + 30min cooldown per direction (bridge)
  → Gate 4: GBM side must agree with local-extreme side (EA)
  → Entry: MARKET at M5 bar close
  → SL: 5 pips, Trail: 5 pips, Timeout: 60 min (12 bars)
```

## Broker tick availability (RoboForex ECN, probed 2026-06-05)
- 2025-01 to 2025-11: NO DATA
- 2025-12: OK (~48k ticks)
- 2026-01 to 2026-03: NO DATA
- 2026-04 to 2026-06: OK (~55k–120k ticks/day)

## EA version history
- v1.10: basic working EA, missing features, bb_pctB=0.5, side bug, no Stage 1
- v1.20: fixed cooldown key, fixed side/class parsing, atomic response write
- v1.30: added all 70 features, UTC fix, Stage 1 still missing → 565 trades/35d
- v1.40: ZZ pivot as signal trigger (WRONG) → 33 trades/35d
- v1.50 (current): local-3 gate + Stage 1 in bridge + all 70 features correct

**Why:** each version fixed implementation bugs while missing the fundamental data mismatch. Contract doc + calibration are the final pieces.
