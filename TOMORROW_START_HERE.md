# Tomorrow: The One Fix That Matters

Date written: 2026-06-04
Context: End of session after 3 failed attempts at the universe alignment problem.

---

## What this session will fix

The GBM was trained on ZigZag D12/Dev5/Back3 confirmed pivot bars (~12/day on EURUSD M5).
The EA currently calls the bridge for every local-3 extreme bar (~800/day, 55% of all bars).
That is a 65x universe mismatch. No amount of calibration or threshold tuning fixes this.
62% of trades hit SL because the GBM is being asked to score bars it was never trained on.

This session replaces the Gate 1 candidate filter in the EA.

---

## The exact approach

**Do NOT trigger on ZZ pivot confirmation** (v1.40 mistake — fires 12+ bars late, entry is gone).

**Do NOT use local-3 extreme as the primary gate** (current v1.50 — 65x too many bars).

**Do this instead:**

On each new M5 bar close, check whether the bar that just completed is near the current
building ZZ tip. Specifically:

1. Load the ZigZag D12/Dev5/Back3 indicator buffer (same handle used for features).
2. On bar close (index 1 = most recently closed bar), walk back up to Back3=3 bars to see
   if any of those bars has a non-zero ZZ buffer value (i.e., the ZZ tip is being built there).
3. If yes — this bar is in the ZZ formation zone. Send to bridge.
4. If no — skip. Do not call the bridge.

This replicates the exact population the GBM saw during training: bars where the ZZ was
actively forming its current pivot extreme. The ZZ does not fire a confirmed signal — it
identifies which bars are the candidates.

---

## Files to edit

**Primary: /home/cmake/Vector/VECTOR003.mq5**

- Current version: v1.50
- Target version: v1.60
- Change: Replace Gate 1 (`IsLocalExtreme(1, 3)`) with ZZ-proximity check
- The ZZ indicator handle is already loaded in the EA for feature collection — reuse it
- Look for the `OnTick` / `OnBar` section where `IsLocalExtreme` gates the bridge call
- Replace with a function `IsNearZZTip(int bar_shift)` that inspects the ZZ buffer

**Do NOT change:**
- /home/cmake/Vector/VECTOR003_BRIDGE.py — Stage 1 filter stays as-is
- /home/cmake/Vector/models/gbm_*.pkl — models are correct, do not retrain
- /home/cmake/Vector/research/EURUSD_M5_CALIBRATED_PANEL.csv.gz — calibration is done

---

## What success looks like

After the fix, run a 35-day Strategy Tester backtest (same window used for all prior versions).

Expected metrics (derived from Python OOS backtest, script 81):
- Trade count: 12-25 trades/day (not 800, not 33)
- Win rate: approximately 47-52%
- Average pip outcome: positive (model has +274p/mo edge when fed correct bars)

If trade count is still ~800/day: the ZZ-proximity gate is not working, debug the buffer read.
If trade count is ~33/day: accidentally triggered on ZZ confirmation again, not formation zone.
If trade count is 12-25/day and WR is near 47%: fix is working, proceed to live forward test.

---

## Context for the session

- Calibration is complete. DST-corrected broker tick data merged. Models retrained 2026-06-05.
- The calibrated panel is at: /home/cmake/Vector/research/EURUSD_M5_CALIBRATED_PANEL.csv.gz
- Models are at: /home/cmake/Vector/models/gbm_*.pkl
- All 70 features are correctly computed in the EA (fixed in v1.30+).
- Stage 1 OR-ensemble lives in the bridge and is working correctly.
- The ONLY remaining problem is Gate 1 sourcing the wrong bar universe.

Do not attempt anything else until this one fix is verified in backtesting.
