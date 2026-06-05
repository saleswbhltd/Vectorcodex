---
name: external-tick-data-calibration-rule
description: Hard rule for all forex EA research — external tick data (Dukascopy etc.) MUST be calibrated to match broker time and DST before use
metadata:
  type: feedback
---

## Rule: External tick data must be calibrated to broker before any EA research or testing

**Why:** Dukascopy stores tick data in UTC. Most retail brokers use EET/EEST (Eastern European Time):
- Winter (Nov–Mar): UTC+2 — subtract 2h from broker timestamps to get UTC
- Summer (Apr–Oct): UTC+3 — subtract 3h from broker timestamps to get UTC

A fixed 3h offset applied year-round is WRONG. This was confirmed by High/Low cross-correlation:
- December 2025 (winter): offset -2h → rho=1.0000 (perfect match)
- April-June 2026 (summer): offset -3h → rho=1.0000 (perfect match)
- Wrong offset (0h): rho=0.25 (random noise — completely misaligned)

The 1-hour DST error caused the VECTOR003 calibration to compare completely different bars, making the tick feature calibration useless.

**How to apply:**
1. Before any external tick data is used with broker data: run the offset sweep using High/Low Spearman correlation
2. Verify rho > 0.90 at the correct offset before proceeding
3. Use DST-aware per-timestamp conversion (not a fixed offset)
4. Keep the calibrated file labeled clearly (see CALIBRATED DATA section below)

## Calibrated tick data — VECTOR003 project

**File:** `/home/cmake/Vector/research/EURUSD_M5_CALIBRATED_PANEL.csv.gz`
**Created:** 2026-06-05
**Source:** Dukascopy M5 OHLC + tick features, calibrated to RoboForex ECN broker
**Calibration source:** 
  - Dec 2025 broker ticks (UTC+2 winter) → 952,890 ticks
  - Apr-Jun 2026 broker ticks (UTC+3 summer) → 3,802,746 ticks
**Offset validation:** rho=1.0000 at correct per-season offset
**Tick feature calibration:** quantile normalization (200-quantile), all 15 tick features
**Models trained on this panel:** `/home/cmake/Vector/models/gbm_*.pkl` (retrained 2026-06-05)

**DO NOT re-use the old uncalibrated panel** (`EURUSD_M5_FULL_PANEL.csv.gz`) for any future EA testing. Always use the calibrated version or generate a fresh calibrated one.

## General rule for all forex EA projects

> **Any forex EA that uses external tick data (Dukascopy, TickStory, etc.) alongside broker data MUST:**
> 1. Identify the broker's UTC offset per season (EET/EEST or equivalent)
> 2. Verify alignment using High/Low Spearman correlation (target rho > 0.90)
> 3. Apply DST-aware UTC conversion (NOT a fixed offset)
> 4. Calibrate feature distributions via quantile normalization
> 5. Verify calibration quality with KS test before retraining models

**Calibration script:** `/home/cmake/Vector/research/84_calibrate_tick_features.py`
**Offset detection script:** use High/Low rho sweep in that script (section D)
