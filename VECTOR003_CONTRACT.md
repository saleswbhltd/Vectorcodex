# VECTOR003 — Implementation Contract

**Purpose:** This document is the authoritative specification that the EA + bridge must match exactly. Every implementation decision must be traceable to this contract. Update this when the research changes; update the code when this changes.

---

## 1. Confirmed OOS Edge (gate: is the model real?)

Re-verified using `research/81_market_vs_limit.py` on stored pkl models vs OOS candidates:

| Spread | Method | WR | Edge | P&L/mo |
|---|---|---|---|---|
| 1.0p | MARKET @ bar close | 47.7% | +1.21p/trade | **+274 pips/month** |
| 1.5p | MARKET @ bar close | 45.5% | +0.80p/trade | +182 pips/month |

- **OOS period:** 2026-03-01 to 2026-06-01 (3 months)
- **Trade count:** ~227 trades/month
- **Entry rule:** market order at the M5 candidate bar's CLOSE price
- **SL:** 5 pips fixed
- **Trail:** 5 pips (trailing stop activated immediately, trails behind max-favorable)
- **Time stop:** 12 M5 bars (60 minutes)
- **Spread assumed:** 1.0 pip (EA spread = bid–ask at fill)
- **Cooldown:** 30 minutes per direction (BUY and SELL tracked independently)

**Model is sound.** The EA is the problem if live results diverge.

---

## 2. Signal Pipeline (exact order matters)

```
Every new M5 bar close
         │
         ▼
[GATE 1] Local-3 extreme check (EA-side, cheap)
   bar must be local HIGH or LOW over last 3 M5 bars
   BUY side:  low[t] == min(low[t-2 : t+1])
   SELL side: high[t] == max(high[t-2 : t+1])
   If neither → skip (no bridge call)
         │
         ▼
[GATE 2] Stage 1 OR ensemble (bridge-side, per class)
   For each of 8 trade_context classes:
     Fire if ANY of K indicators is in the pivot zone
     (zone thresholds from DEV pivot distribution — see Section 4)
   If bar passes Stage 1 for ≥1 class → proceed to GBM
   If passes no class → return fire=false immediately
         │
         ▼
[STAGE 2] GBM scoring (bridge-side)
   Run 8 per-class HistGradientBoostingClassifier models
   best_class = argmax(prob across 8 classes)
   best_prob  = max prob
   side       = label_to_side[class_to_label[best_class]]
         │
         ▼
[GATE 3] Threshold + cooldown (bridge-side)
   best_prob >= 0.70 (MODERATE; adjust for risk preference)
   cooldown: 30min elapsed since last same-direction signal
         │
         ▼
[GATE 4] GBM side must match local-extreme side (EA-side)
   If GBM says BUY but bar is only a local HIGH → discard
   (defense in depth against GBM misfires)
         │
         ▼
[ENTRY] Market order at current bar's CLOSE price
```

---

## 3. Stage 1 — Exact Thresholds Per Class

Source: `research/stage1_thresholds.json` (computed from DEV pivot distribution, scripts 41/56).
Each rule fires if `indicator direction threshold`. Bar passes Stage 1 if ANY rule fires (OR).

### BEAR_CONTINUATION_LOW (BUY side) — zone=70%, K=5
| Indicator | Direction | Threshold |
|---|---|---|
| rsi14 | <= | 37.742 |
| dist_ema20_atr | <= | -1.430 |
| bb_pctB | <= | 0.145 |
| dist_ema50_atr | <= | -2.034 |
| stoch_k | <= | 17.688 |

### BULL_TREND_BREAK_LOW (BUY side) — zone=70%, K=5
| Indicator | Direction | Threshold |
|---|---|---|
| rsi14 | <= | 37.783 |
| dist_ema20_atr | <= | -1.371 |
| bb_pctB | <= | 0.141 |
| minus_di | >= | 28.815 |
| dist_ema50_atr | <= | -2.054 |

### BUY_PULLBACK_UPTREND (BUY side) — zone=60%, K=5
| Indicator | Direction | Threshold |
|---|---|---|
| stoch_k | <= | 26.462 |
| macd_hist | <= | -0.00005 |
| h1_ema50_slope_pips | >= | 18.456 |
| h1_dist_ema200_pips | >= | 50.321 |
| williams_r14 | <= | -76.923 |

### WEAK_LOW_IN_DOWNTREND (BUY side) — zone=80%, K=3
| Indicator | Direction | Threshold |
|---|---|---|
| h1_ema200_slope_pips | <= | -4.127 |
| h1_dist_ema200_pips | <= | -13.557 |
| h1_ema50_slope_pips | <= | -8.978 |

### BULL_CONTINUATION_HIGH (SELL side) — zone=70%, K=5
| Indicator | Direction | Threshold |
|---|---|---|
| rsi14 | >= | 61.887 |
| dist_ema20_atr | >= | 1.394 |
| dist_ema50_atr | >= | 2.153 |
| plus_di | >= | 28.874 |
| stoch_k | >= | 82.371 |

### BEAR_TREND_BREAK_HIGH (SELL side) — zone=80%, K=5
| Indicator | Direction | Threshold |
|---|---|---|
| rsi14 | >= | 58.959 |
| dist_ema20_atr | >= | 1.007 |
| dist_ema50_atr | >= | 1.490 |
| minus_di | <= | 16.792 |
| bb_pctB | >= | 0.777 |

### SELL_PULLBACK_DOWNTREND (SELL side) — zone=80%, K=3
| Indicator | Direction | Threshold |
|---|---|---|
| h1_dist_ema200_pips | <= | -18.951 |
| h1_ema200_slope_pips | <= | -3.230 |
| h1_ema50_slope_pips | <= | -8.416 |

### WEAK_HIGH_IN_UPTREND (SELL side) — zone=70%, K=3
| Indicator | Direction | Threshold |
|---|---|---|
| h1_ema50_slope_pips | >= | 15.799 |
| macd_hist | >= | 0.00003 |
| stoch_k | >= | 68.810 |

---

## 4. Stage 2 — GBM Models

- 8 `HistGradientBoostingClassifier` pkl files in `models/gbm_<CLASS>.pkl`
- Each pkl stores: `{model, features, feature_medians}`
- Missing features → fill with `feature_medians[feat]` (NOT 0, NOT global median)
- **feature order matters** — use `manifest.json feature_lists[class]` order exactly

### Class → side mapping
```
HH: SELL   (BULL_CONTINUATION_HIGH, BEAR_TREND_BREAK_HIGH)
LH: SELL   (WEAK_HIGH_IN_UPTREND, SELL_PULLBACK_DOWNTREND)
HL: BUY    (BUY_PULLBACK_UPTREND, WEAK_LOW_IN_DOWNTREND)
LL: BUY    (BULL_TREND_BREAK_LOW, BEAR_CONTINUATION_LOW)
```

---

## 5. Feature Computation — What the EA Must Send

All 70 features must be computed at the **M5 bar that is the local-3 extreme** (the candidate bar, `shift=1` in most cases). Features must match `research/35_build_full_panel.py` and `research/34_tick_features.py` exactly.

### Time correction (CRITICAL — DST-AWARE)
Research data is Dukascopy UTC. Broker uses EET/EEST — NOT a fixed offset:
- Winter (Nov–Mar): UTC+2 → subtract 2h from broker time
- Summer (Apr–Oct): UTC+3 → subtract 3h from broker time

Confirmed by High/Low Spearman rho = 1.0000 at correct per-season offset.
A fixed 3h offset applied year-round is WRONG for winter months.

In the EA (MQL5), `TimeCurrent() - TimeGMT()` gives the actual offset at runtime,
so it automatically handles DST:
```
bar_utc = bar_broker_time - (TimeCurrent() - TimeGMT())
hour_utc = bar_utc.hour
dow      = bar_utc.day_of_week
```

For offline data processing (Python): use `broker_to_utc()` in `84_calibrate_tick_features.py`
which applies month-based DST correction per timestamp.

### Tick features (script 34) — from CopyTicksRange over the candidate bar
| Feature | Formula |
|---|---|
| tick_count | n ticks in bar (fallback: iTickVolume) |
| median_tick_interval_ms | median(time_msc[i] - time_msc[i-1]) |
| max_tick_interval_ms | max(time_delta_ms) |
| spread_avg | mean((ask-bid)/pip per tick) |
| spread_max | max((ask-bid)/pip per tick) |
| bid_aggressor_pct | 100 × mean(bid[i] > bid[i-1]) |
| ask_aggressor_pct | 100 × mean(ask[i] < ask[i-1]) |
| imbalance | bid_aggressor_pct − ask_aggressor_pct |
| tick_velocity_first_half | sum(abs(mid_change)/pip, first n/2 ticks) / (n/2) |
| tick_velocity_second_half | same, second half |
| vel_ratio_2nd_to_1st | second / first |
| max_run_up_pips_intrabar | (cummax(mid) − mid[0]) / pip |
| max_run_dn_pips_intrabar | (mid[0] − cummin(mid)) / pip |
| ticks_at_high_pct | % ticks within 1 pip of bar high |
| ticks_at_low_pct | % ticks within 1 pip of bar low |

### Rolling OHLC features (script 35) — exact formulas
| Feature | Formula | Notes |
|---|---|---|
| atr_ratio_5_50 | ATR5 / ATR50 | |
| atr_pct100 | percentile rank of ATR14 in last 100 bars | 0–1 |
| bb_pctB | (close − bb_lo) / (bb_up − bb_lo) | 20-bar Bollinger |
| bb_squeeze | bb_width_pips / rolling50_mean(bb_width) | |
| realized_vol_20 | std(pct_change, 20 bars, ddof=1) × 1e4 | |
| range_z20 | (range − rolling20_mean) / rolling20_std | ddof=1 |
| vol_z20 | (tick_volume − rolling20_mean) / rolling20_std | ddof=0 |
| vol_of_vol_20 | rolling20_std(ATR14) | ddof=1 |
| consec_up | consecutive bars where close > open | count from bar[s] |
| consec_dn | consecutive bars where close < open | count from bar[s] |
| velocity_3 | close[s] − close[s+3] | price units (not pips) |
| accel | velocity_3[s] − velocity_3[s+1] | price units |

### H1 features
- Use H1 bar that CONTAINS the M5 pivot bar time (`iBarShift` on pivot bar time)
- `h1_ema50_slope_pips` / `h1_ema200_slope_pips`: difference over 24 H1 bars
- `h1_dist_24h_high_pips`: `(rolling24_H1_high − h1_close) / pip`
- `h1_dist_24h_low_pips`: `(h1_close − rolling24_H1_low) / pip`
- `h1_bb_pctB`: Bollinger %B on H1 close (20-bar H1 Bollinger)

---

## 6. Architecture Decision

**Stage 1 lives in the bridge, not the EA.**

Rationale: Stage 1 thresholds are Python floats from the research. Implementing 8×5 = 40 threshold rules in MQL5 is fragile and hard to verify. The bridge loads `stage1_thresholds.json` at startup and checks Stage 1 before running GBMs.

EA responsibilities:
1. Detect local-3 extreme on every new M5 bar
2. Compute 70 features at the candidate bar
3. Send to bridge, wait for response
4. Execute trade if fire=true and GBM side matches local-extreme side

Bridge responsibilities:
1. Check Stage 1 (OR ensemble per class) → if no class passes, return fire=false immediately
2. Run GBM for classes that pass Stage 1
3. Apply threshold (0.70) + cooldown
4. Return: fire, side, best_class, best_prob

---

## 7. What Was Wrong in Each EA Version

| Version | Bug | Effect |
|---|---|---|
| v1.10 | `bb_pctB=0.5` hardcoded, 29/70 features missing, `hour_utc` = broker time, cooldown disabled | Everything wrong |
| v1.20 | Cooldown field mismatch (`last_signal_time_unix` ≠ `last_buy/sell_signal_unix`) | 2× trades, no Stage 1 |
| v1.30 | Tick features added, UTC fix, cooldown fixed — but Stage 1 still missing, local-3 alone → 3× too many signals above threshold | 565 trades vs 227 expected |
| v1.40 | ZZ pivot as signal trigger | Wrong — ZZ = labeling tool only; only 33 trades |
| **v1.50** | **Stage 1 in bridge + local-3 EA + all features correct** | **Target** |

---

## 8. Verification Checklist Before Live

- [ ] Feature parity: log EA feature vector at a known pivot bar, diff vs research panel at same UTC timestamp
- [ ] Stage 1 fires at correct rate: ~57–124 bars/day per class in bridge log (not per trade, per candidate)
- [ ] Trade count: ~200–230 trades/month at MODERATE (thr=0.70, cd=30min)
- [ ] Win rate: ~47–50% on a multi-month backtest (every-tick, 1p spread)
- [ ] No `parse response failed` in EA journal
- [ ] Bridge response time < 50ms (models are loaded, no cold-start)

---

## 9. Files

| File | Role |
|---|---|
| `research/stage1_thresholds.json` | Stage 1 OR ensemble rules, loaded by bridge at startup |
| `models/gbm_<CLASS>.pkl` | Trained GBMs + feature list + medians |
| `models/manifest.json` | Class→label→side mappings, default params |
| `VECTOR003.mq5` | EA: local-3 gate + 70-feature computation + bridge comms |
| `VECTOR003_BRIDGE.py` | Bridge: Stage 1 + GBM + threshold + cooldown |
| `research/81_market_vs_limit.py` | Authoritative OOS P&L simulation |
| `research/stage1_thresholds.json` | Per-class Stage 1 rules |
