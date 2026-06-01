# CLAUDE.md — Vector

## What this project is

**VECTOR001** — SMC-inspired structural EA. H4 reads major bias, H1 ZigZag generates entry signals (BOS + ChoCh both directions), OB limit order entry with market fallback.

This is a **different concept** from OTT001 (mean-reversion). VECTOR001 trades structural breaks with TP at next H1/H4 swing level.

## Files

| File | Role |
|------|------|
| `VECTOR001.mq5` | The EA — compile and attach to EURUSD M5 |
| `VECTOR001_step1_research.py` | Step 1 signal frequency research (Python, uses H1 data) |
| `deploy.sh` | Copy EA to MT5 Advisors/ folder |

## Include dependencies (in MT5)

EA lives in `Experts/Advisors/`. Includes reference `../SMCEA/`:

```mql5
#include "../SMCEA/SMCEA_Risk.mqh"
#include "../SMCEA/SMCEA_Manager.mqh"
#include "../SMCEA/MTF.mqh"
```

SMCEA includes are at:
`/mnt/c/Users/cmake/AppData/Roaming/MetaQuotes/Terminal/5FFA568149E88FCD5B44D926DCFEAA79/MQL5/Experts/SMCEA/`

Source copies also in `/home/cmake/SMCtrade/` (shared with SMCEA_V4).

## Deploy

```bash
cd /home/cmake/Vector
bash deploy.sh
# Then in MetaEditor: open VECTOR001.mq5, press F7
```

## Strategy

- **H4 bias**: `CStructureEngine` (fractal, left=10 right=3) — bull or bear
- **H1 signals**: `CH1PivotTracker` — pip-threshold ZigZag (default 30pip)
  - ZZ turns UP → BULL signal (swing LOW confirmed)
  - ZZ turns DOWN → BEAR signal (swing HIGH confirmed)
  - ~19 signals/month at 30pip, ~8/month at 50pip
- **Entry**: OB limit order at OB zone, market fallback after `InpFallbackBars` H1 bars
- **SL**: Beyond OB edge + buffer
- **TP1**: Nearest H1 ZZ swing level at min RR
- **TP2**: Furthest H4 swing level (2-slot: 60%/40%)
- **With-trend**: standard risk (1%), min RR 1.5
- **Counter-trend**: half risk (0.5%), min RR 2.5

## Key inputs

| Input | Default | Notes |
|-------|---------|-------|
| `InpH1ThreshPips` | 30.0 | ZigZag flip threshold — lower = more signals |
| `InpRiskPct` | 1.0 | % equity with-trend |
| `InpCounterRiskPct` | 0.5 | % equity counter-trend |
| `InpMinRR` | 1.5 | Min RR with-trend |
| `InpCounterMinRR` | 2.5 | Min RR counter-trend |
| `InpFallbackBars` | 3 | H1 bars before limit → market |
| `InpArrowsOnly` | false | Visual signal test mode |

## Build status

| Step | Task | Status |
|------|------|--------|
| 1 | Research — ZZ params, signal freq, OB retracement | ✅ DONE |
| 2 | Structure engine + ZZ signal source | ✅ DONE |
| 3 | Entry engine (OB finder, limit/market) | ✅ DONE |
| 4 | SL/TP engine | ✅ DONE |
| 5 | Position sizing (CRiskManager) | ✅ DONE |
| 6 | Signal baseline test — arrows visual check | ✅ DONE |
| 7 | Full 12-month backtest validation | ⬜ Next |
