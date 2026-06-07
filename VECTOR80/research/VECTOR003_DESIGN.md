# VECTOR003 — Multi-Engine Pivot Architecture

## Concept

One EA, four independent pivot engines. Each engine detects its **target pivot type** with custom logic and emits qualified signals into a shared event queue.

```
┌─────────────────────────────────────────────────────────────┐
│ VECTOR003 EA                                                │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   ┌─────────────────┐    ┌─────────────────┐               │
│   │ BUY_SWING       │    │ SELL_SWING      │               │
│   │ Engine          │    │ Engine          │               │
│   │  (LL pivots)    │    │  (HH pivots)    │               │
│   └────────┬────────┘    └────────┬────────┘               │
│            │                      │                         │
│   ┌────────┴────────┐    ┌────────┴────────┐               │
│   │ BUY_PULLBACK    │    │ SELL_PULLBACK   │               │
│   │ Engine          │    │ Engine          │               │
│   │  (HL pivots)    │    │  (LH pivots)    │               │
│   └────────┬────────┘    └────────┬────────┘               │
│            │                      │                         │
│            ▼                      ▼                         │
│   ┌─────────────────────────────────────────┐              │
│   │  Signal Router / Position Manager        │              │
│   │  - dedupe overlapping signals            │              │
│   │  - apply position-count limits           │              │
│   │  - route by engine type to risk profile  │              │
│   └─────────────────────────────────────────┘              │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## Engine specifications

Each engine has:
- **Target type** (LL/HL/HH/LH)
- **Detection algorithm** (rules + classifier output threshold)
- **Quality score** (0-1, derived from classifier probability or rule count)
- **Expected behavior** (deep reversal vs continuation)
- **Risk profile** (SL/TP/timeout calibrated to that pivot's typical MFE/MAE)

### BUY_SWING Engine
- Target: LL (deep low, major reversal)
- Detection: GBM probability ≥ THR_SWING using RSI/Stoch/Williams extremes + tick exhaustion features
- Risk profile: wider SL (15-20p), bigger TP (40-60p), longer timeout (2-4h)
- Use case: catch the bottom of a sustained decline

### BUY_PULLBACK Engine
- Target: HL (continuation low in uptrend)
- Detection: trend-aligned + measured retracement signature
- Hard gates: H1 uptrend, M5 above EMA50, ADX > 18
- Risk profile: tighter SL (8-10p), modest TP (15-20p), short timeout (1-2h)
- Use case: buy the dip in established trend

### SELL_SWING Engine (mirror of BUY_SWING)

### SELL_PULLBACK Engine (mirror of BUY_PULLBACK)

## Per-engine logging

Each signal carries metadata:
- engine_id
- pivot_type (HH/HL/LH/LL)
- side (BUY/SELL)
- role (SWING/PULLBACK)
- probability (raw classifier output)
- expected MFE / MAE bands
- regime context (H1 trend dir, ATR band)

CSV columns added vs VECTOR002:
- `engine_id`, `role`, `target_type`, `gbm_probability`, `regime_h1_trend`

## Decision routing

Position Manager logic:
1. Pivot detected by engine X with score S
2. If S < threshold for that engine type → discard
3. If existing position in same direction within last N min → block
4. If portfolio at max open trades → block
5. Otherwise: place trade with engine-specific SL/TP profile

## Engine portability to MQL5

Three options for porting the classifier:

**A. Rule-extraction** (cleanest)
- Train sklearn DecisionTreeClassifier per type (depth 8, min_leaf 30)
- Extract leaf rules as nested if-then-else
- Hand-code rules in MQL5
- Loss vs GBM: 5-15% precision typically

**B. Manual logistic regression** (transparent)
- Train logistic regression on standardized features
- Extract weights
- Score = sigmoid(intercept + Σ w_i × z_i)
- Direct port: arithmetic on standardized values

**C. ONNX export + ONNX Runtime** (full GBM precision)
- Export GBM to ONNX
- Load in MQL5 via ONNX runtime (available since MT5 build 3811)
- Full classifier precision preserved
- More complex to integrate

Recommendation: **Start with option A** for VECTOR003 v1. Option B/C if precision proves insufficient.

## Roadmap

1. ✅ Build 4 hand-rule engines (step 37) — baseline 10-13% precision
2. ⏳ Train per-type GBM with M5+H1+TICK (step 36 running)
3. ⏳ Extract decision rules from per-type Decision Trees
4. ⏳ Code VECTOR003.mq5 with 4 engines + position manager
5. ⏳ Backtest against 2026 OOS data
6. ⏳ Paper trade
