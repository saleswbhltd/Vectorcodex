# VECTOR003 Deployment Guide

## What you're deploying

A **two-process** trading system:
- **VECTOR003.mq5** — MT5 Expert Advisor (sits on M5 EURUSD chart)
- **VECTOR003_BRIDGE.py** — Python bridge that runs 8 GBM classifiers

The EA queries the bridge once per M5 bar via file-based JSON messages. The bridge returns a decision (fire / no-fire + side + probability). The EA executes the trade.

---

## Files

| File | Location | Purpose |
|---|---|---|
| `VECTOR003.mq5` | `/home/cmake/Vector/` | EA source |
| `VECTOR003_BRIDGE.py` | `/home/cmake/Vector/` | Python bridge |
| `VECTOR003.set` | MT5 `\Profiles\Tester\` | Parameter preset |
| `manifest.json` | `/home/cmake/Vector/models/` | Class/feature manifest |
| `gbm_<class>.pkl` × 8 | `/home/cmake/Vector/models/` | Trained models (~7 MB total) |
| `VECTOR003_SPEC.md` | `/home/cmake/Vector/research/` | Strategy specification |

---

## Quick start

### 1. Deploy the EA (already done)

```bash
bash /home/cmake/Vector/deploy_v3.sh
```

This copies `VECTOR003.mq5` to your MT5 Advisors directory.

### 2. Compile in MetaEditor

- Open MetaEditor (F4 from MT5)
- Navigate to Experts/Advisors/VECTOR003.mq5
- Press F7 to compile
- Expect 0 errors. Warnings about unused indicator handles are OK.

### 3. Start the Python bridge

```bash
python3 /home/cmake/Vector/VECTOR003_BRIDGE.py
```

Expected output:
```
[2026-06-03 17:00:00] ============================================================
[2026-06-03 17:00:00] VECTOR003 Bridge starting
[2026-06-03 17:00:00] ============================================================
[2026-06-03 17:00:00] Loading manifest...
[2026-06-03 17:00:00]   classes: 8
[2026-06-03 17:00:00]   loaded BULL_CONTINUATION_HIGH: 70 features
...
[2026-06-03 17:00:00] Total models loaded: 8
[2026-06-03 17:00:00] Polling /mnt/c/Users/cmake/AppData/Roaming/MetaQuotes/Terminal/Common/Files/vector003_request.json every 0.1s
```

Keep this terminal open. The bridge must be running for the EA to receive signals.

### 4. Attach the EA to the chart

In MT5:
- Open EURUSD M5 chart
- Drag VECTOR003 from Navigator → Experts/Advisors onto the chart
- In the Inputs tab, click "Load" → select `VECTOR003.set` (or use defaults)
- Click OK
- Verify "AutoTrading" button is ON (green)

### 5. Monitor

- Bridge terminal shows incoming requests and decisions
- MT5 Experts tab shows EA logs
- Chart panel shows live state (signals fired, open positions)
- Arrow markers appear on each entry

---

## Operating modes (preset variants)

The defaults in `VECTOR003.set` are MODERATE. To switch modes, edit Inputs:

| Mode | Threshold | Cooldown | Local N | Expected trades/mo | Win | P&L/mo (1p spread) |
|---|---|---|---|---|---|---|
| CONSERVATIVE | 0.80 | 60 | 3 | ~127 | 57% | +335 pips |
| **MODERATE** (default) | **0.70** | **30** | **3** | **~182** | **51%** | **+245 pips** |
| AGGRESSIVE | 0.60 | 30 | 3 | ~227 | 48% | +274 pips |

---

## Live trading checklist

Before running on a live account:

- [ ] Bridge running and connected (check logs for `[...] FIRE` events)
- [ ] EA compiled with no errors
- [ ] AutoTrading enabled in MT5
- [ ] Initial paper trade run: at least 2 weeks on demo account
- [ ] Confirm broker spread ≤ 1.5 pips average during trading hours
- [ ] News calendar checked for the week ahead
- [ ] Daily risk limit configured (5% equity / day pause)
- [ ] Position sizing tested with InpRiskPct=0.5% first

---

## Bridge communication protocol

Request from EA → Bridge:

```json
{
  "request_id": "1",
  "bar_time_unix": 1762272000,
  "threshold": 0.70,
  "cooldown_min": 30,
  "last_buy_signal_unix": 1762270200,
  "features": {
    "rsi14": 67.4,
    "atr5": 8.2,
    "bb_pctB_real": 0.88,
    ...
  }
}
```

Response from Bridge → EA:

```json
{
  "fire": true,
  "best_class": "BEAR_CONTINUATION_LOW",
  "best_prob": 0.84,
  "side": "BUY",
  "all_probs": { "BULL_CONTINUATION_HIGH": 0.12, ... },
  "request_id": "1",
  "timestamp": "2026-06-03T17:00:42.123"
}
```

File locations (Windows):
- Request:  `C:\Users\cmake\AppData\Roaming\MetaQuotes\Terminal\Common\Files\vector003_request.json`
- Response: `C:\Users\cmake\AppData\Roaming\MetaQuotes\Terminal\Common\Files\vector003_response.json`
- Bridge log: `C:\Users\cmake\AppData\Roaming\MetaQuotes\Terminal\Common\Files\vector003_bridge.log`

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| EA log: "V3 BRIDGE: timeout after 3000 ms" | Bridge not running | Start `VECTOR003_BRIDGE.py` |
| Bridge log: "missing model" | Models not exported | Run `python3 82_train_export_final.py` |
| EA log: "lots calc failed" | Symbol not valid or 0 equity | Check symbol + account state |
| No signals firing | Threshold too high OR no local extremes | Lower threshold OR check market is moving |
| EA fires too often | Threshold too low | Raise threshold to 0.80 |

---

## Updating the models

When you have more data (e.g. 6 more months), retrain:

```bash
# 1. Pull new data through the pipeline
cd /home/cmake/Vector/research
python3 65_multi_engine_union.py        # rebuild candidates
python3 82_train_export_final.py        # retrain + export

# 2. Restart the bridge (it caches models in memory)
# (Ctrl+C the running bridge, then re-run)
```

The EA does NOT need recompilation — it just calls the bridge over JSON.

---

## What the EA does (one-pager summary)

```
EVERY M5 BAR CLOSE:
  ↓
  Check: is bar a local high (over last 3 M5 bars)?  → potential SELL
  Check: is bar a local low?                          → potential BUY
  If neither: SKIP (no bridge call)
  ↓
  Build feature vector (70 indicator values)
  ↓
  Write vector003_request.json
  Wait for vector003_response.json (≤ 3 sec)
  ↓
  Parse: fire?, side, probability, best_class
  ↓
  If fire AND local-extreme AND cooldown elapsed:
      MARKET order, +5p SL, immediate trail at 5p behind max-favorable
      Time stop: close at +60 min if neither SL nor manual close
      Risk-based sizing using InpRiskPct
```

Average runtime per bar: ~50ms (bridge inference) + ~10ms (EA logic).

---

## Performance expectations (from walk-forward validation)

**11 monthly windows (Jul 2025 → May 2026), MODERATE mode (idealized fills):**

| Metric | Value |
|---|---|
| Months profitable | 11/11 |
| Mean win rate | 72.6% ± 5.4% |
| Mean monthly P&L | +764 ± 200 pips |
| Mean edge | +4.25 ± 0.83 pips/trade |
| Mean trade count | 182 ± 37 per month |
| Worst month | Aug 2025: 64.8% win, +555 pips |
| Best month | Jul 2025: 80.9% win, +1107 pips |

**Realistic at 1.0 pip broker spread:**

| Metric | Value |
|---|---|
| Win rate | ~50% |
| Monthly P&L | ~+245-274 pips |
| Trade count | ~160-230 per month |
| Edge per trade | ~+1.5p |

**Initial risk budget recommendation:** start with `InpRiskPct=0.5%`. After 1 month of stable performance, optionally raise to 1.0%.

---

## Stop using if...

- 2 consecutive months with win rate < 40% → strategy degraded, pause and re-analyze
- 1 month with P&L < −500 pips → review broker conditions and spread
- Bridge regularly timing out → infrastructure issue, fix before re-engaging
