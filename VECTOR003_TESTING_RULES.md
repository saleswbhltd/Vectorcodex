# VECTOR003 — Testing Rules & Pre-flight Checklist

**Run through this before every Strategy Tester run or live test.**
Prevents repeating resolved bugs and wasting backtest time on broken configs.

---

## Pre-flight checklist

- [ ] Bridge running and fresh? `python3 -c "import json,time; d=json.load(open('/mnt/c/Users/cmake/AppData/Roaming/MetaQuotes/Terminal/Common/Files/vector003_bridge.heartbeat')); print(f'age={time.time()-d[\"ts\"]:.0f}s')"`
- [ ] Bridge startup log shows **"Stage 1 rules loaded: 8 classes"**
- [ ] EA journal shows `VECTOR003 v1.5X ready  thr=0.70 cd=30min local=3`
- [ ] EA journal shows `Bridge state: OK  hb_age=0.Xs`
- [ ] Models broker-calibrated? `grep broker_retrained /home/cmake/Vector/models/manifest.json`
- [ ] `parse response failed` count = 0 in journal

---

## What each journal/log line tells you

| Line | Meaning | Status |
|---|---|---|
| `v1.5X ready  thr=0.70 cd=30min local=3` | Correct version compiled | ✓ GOOD |
| `Bridge state: OK  hb_age=0.Xs` | Bridge alive, UTC heartbeat match | ✓ GOOD |
| `Stage 1 rules loaded: 8 classes` | Stage 1 loaded in bridge | ✓ GOOD |
| `FIRE  BUY  class=BEAR_CONTINUATION_LOW  prob=0.78` | Bridge scored correctly | ✓ GOOD |
| `parse response failed` | Atomic write bug or empty response | ✗ STOP |
| `V3 BRIDGE: timeout` | Bridge too slow or not running | ✗ STOP |
| `infinite Sleep loop` | EA timeout too long in tester (use tester mode) | ✗ STOP |
| `Bridge state: DOWN  (last hb ts=0.0)` | Heartbeat not read — check UTC offset | ✗ STOP |
| `V3 ERROR: ZigZag Lines MTF not found` | ZZ indicator missing — ignore, ZZ not used in v1.50 | ignore |

---

## Expected metrics after broker calibration (verified in Python, 1.0p spread)

| Metric | Expected | Action if outside |
|---|---|---|
| Trades/month | 180–250 | <100: Stage 1 too strict. >300: cooldown broken |
| BUY/SELL split | 40/60 to 60/40 | Extreme skew = regime mismatch |
| SL hit rate | 48–55% | >65%: tick calibration failed or data mismatch |
| Timeout rate | 25–35% | Very low = trail not working |
| Trail moves | >0 in every-tick run | 0 trails = trade management bug |
| Run time (35 days, every-tick) | 5–15 min | <3 min: too few bridge calls |

---

## Ideas confirmed WRONG — do not revisit

| Idea | Why wrong |
|---|---|
| ZigZag D12 as real-time signal trigger | ZZ = labeling tool only. Always fires too late. Never in the research pipeline. |
| Local-3 extreme as ONLY pre-filter (no Stage 1) | 13× too many bars vs training universe. Causes GBM to misfire constantly. |
| Run GBM on ALL bars (no Stage 1) | Produces 565 trades/35d vs 227 expected. GBM not trained for this universe. |
| OHLC-only GBMs | Edge lives entirely in tick microstructure. OHLC-only = −366p/mo confirmed. |
| Dukascopy-trained models on broker without calibration | Tick distributions differ → 75% SL rate vs expected 50%. |
| `bb_pctB = 0.5` placeholder | Hardcoded constant kills the feature entirely. |
| `TimeCurrent()` for heartbeat comparison | Broker UTC+3 makes heartbeat look 3h old → bridge always "DOWN". Use `TimeGMT()`. |
| OHLC-only is the same on any broker | True for OHLC. FALSE for tick features — those are broker-specific. |
| Raising threshold to fix over-firing | Does not fix universe mismatch. Only Stage 1 fixes it. |

---

## Calibration pipeline (one-time setup, then models are broker-native)

```bash
# Step 1: export broker ticks in MT5 (VECTOR_BrokerTickExport.mq5 as Script)
#   Run 1: InpFrom=2025.12.01, InpTo=2026.01.01
#   Run 2: InpFrom=2026.04.01, InpTo=2026.06.05

# Step 2: calibrate Dukascopy → broker distributions
cd /home/cmake/Vector/research
python3 84_calibrate_tick_features.py
# Must pass: price alignment < 0.5 pip + KS test p > 0.05 for all features
# Output: EURUSD_M5_CALIBRATED_PANEL.csv.gz + tick_calibration.json

# Step 3: rebuild Stage 1 thresholds + candidates + retrain GBMs
python3 83_broker_rebuild.py
# Auto-detects calibrated panel. Outputs new gbm_*.pkl + manifest.json

# Step 4: restart bridge (picks up new models automatically)
cmd.exe /c "taskkill /F /IM pythonw.exe"
# wait 20s, then bridge auto-restarts via start_bridge.bat

# Step 5: recompile EA (F7 in MetaEditor) + Strategy Tester
```

---

## Verification gates that must pass before trusting any result

1. **Price alignment**: `84_calibrate_tick_features.py` must report mean diff < 0.5 pip
2. **KS test**: all 15 tick features must show p > 0.05 (calibrated ≈ broker)
3. **Trade count**: 180–250/month in Strategy Tester (not 33 and not 565)
4. **No parse failures**: 0 `parse response failed` in journal
5. **Both BUY and SELL fire**: not all one direction

---

## Files that must stay in sync

| File | Contains | Break if out of sync |
|---|---|---|
| `VECTOR003_CONTRACT.md` | Full pipeline specification | EA/bridge diverge from spec |
| `research/stage1_thresholds.json` | Stage 1 OR-ensemble thresholds | Bridge uses wrong gates |
| `models/manifest.json` | Feature lists, class→side mapping | Bridge sends wrong features |
| `research/tick_calibration.json` | Dukascopy→broker quantile maps | Produced by step 84 |
| `VECTOR003_TESTING_RULES.md` | This file | Always keep current |

---

## After successful calibration: new baseline metrics to record

Run a full 35-day Strategy Tester (Apr 30 – Jun 4 2026, every-tick, 1p spread) and record:
- Trade count, BUY/SELL split, SL%, timeout%, trail count, final balance
- Compare to research target: +274p/mo, 47.7% WR, 227 trades/mo
- If within 20% of research → calibration successful → proceed to forward test
