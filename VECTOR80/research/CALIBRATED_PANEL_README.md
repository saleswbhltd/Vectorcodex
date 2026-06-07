# EURUSD_M5_CALIBRATED_PANEL.csv.gz — READ BEFORE USE

## USE THIS FILE. Not the raw Dukascopy panel.

**This is the only panel that should be used for VECTOR003 GBM training and research.**

The raw Dukascopy panel (`EURUSD_M5_FULL_PANEL.csv.gz`) has tick features calibrated
to Dukascopy's own tick distributions. They do NOT match the broker (RoboForex ECN).
Using the raw panel produces models that fail completely in live testing.

---

## What this file is

**Source:** Dukascopy M5 OHLC + tick features for EURUSD, Feb 2025 – Jun 2026  
**Calibration applied:** Dukascopy tick feature distributions → RoboForex ECN distributions  
**Created:** 2026-06-05  
**Script:** `84_calibrate_tick_features.py`

---

## The DST issue (why a fixed 3h offset is wrong)

RoboForex server uses Eastern European Time — NOT a fixed UTC offset:

| Season | Months | Broker offset | Hours to subtract |
|---|---|---|---|
| Summer | April – October | UTC+3 (EEST) | **−3h** |
| Winter | November – March | UTC+2 (EET) | **−2h** |

**Confirmed by High/Low Spearman cross-correlation (rho = 1.0000 at correct offset):**
- December 2025 (winter): best offset = −2h → rho = 1.0000
- April-June 2026 (summer): best offset = −3h → rho = 1.0000
- Wrong offset (0h or fixed): rho ≈ 0.25 (completely misaligned — comparing different bars)

The calibration script (`84_calibrate_tick_features.py`) applies per-timestamp DST-aware
conversion via the `broker_to_utc()` function. This must be used for any future exports.

---

## Calibration data sources

| Period | Ticks | Season | Offset used |
|---|---|---|---|
| December 2025 | 952,890 ticks | Winter (EET) | −2h |
| April – June 2026 | 3,802,746 ticks | Summer (EEST) | −3h |

**Calibration method:** 200-quantile normalization per tick feature  
**Verification:** High/Low Spearman rho = 0.9355 (aligned, up from 0.257 before DST fix)

---

## Models trained on this panel

`/home/cmake/Vector/models/gbm_*.pkl` — retrained 2026-06-05  
OOS AUC: 0.891 – 0.939 across all 8 trade-context classes

---

## General rule for all forex EA research

> **Any project using external tick data (Dukascopy, TickStory, etc.) alongside live broker data MUST:**
> 1. Sweep UTC offsets using High/Low Spearman rho — find exact seasonal offset
> 2. Apply DST-aware per-timestamp conversion (not a fixed offset)
> 3. Verify alignment: rho must be > 0.90 before calibrating
> 4. Calibrate feature distributions via quantile normalization
> 5. Re-verify after calibration with KS tests
> 6. Label all outputs clearly as "calibrated" with the date and source
