"""
Step 1 — Compute standard technical indicators on the EURUSD M5 dataset.

Reads:  /mnt/c/Users/cmake/Documents/MarketData/EURUSD_M5_2025_bars.csv
Writes: /home/cmake/Vector/research/m5_with_indicators.parquet

Indicators chosen for pivot-quality research (each candidate has a clear hypothesis
for *why* it might mark a true reversal vs a noise pivot):

  - RSI(14)              — overbought/oversold extremes around true reversals
  - MACD(12,26,9)        — momentum exhaustion / divergence at pivots
  - Bollinger(20,2)      — band-touch & %B at extremes
  - ATR(14)              — measure of move size leading into pivot
  - ADX(14) +DI -DI      — trend strength at pivot (low ADX = ranging = reversion edge)
  - Stochastic(14,3,3)   — fast momentum oscillator
  - EMA(20,50,200)       — price distance from MAs at pivot
  - Momentum(10)         — ROC-style
  - Candle-pattern flags — pin bar, engulfing, doji (size-aware)
  - Volume (tick_vol)    — surge at pivots vs random bars
  - Wick ratios          — long-wick rejection at pivots

Output is a parquet (compact, fast to reload) with one row per M5 bar.
"""

import pandas as pd
import numpy as np

SRC = "/mnt/c/Users/cmake/Documents/MarketData/EURUSD_M5_2025_bars.csv"
OUT = "/home/cmake/Vector/research/m5_with_indicators.csv.gz"

print("loading...")
df = pd.read_csv(SRC)
df["datetime"] = pd.to_datetime(df["datetime"], format="%Y.%m.%d %H:%M")
df = df.set_index("datetime").sort_index()
df = df.rename(columns={"tick_vol": "volume"})

# Keep only the columns we need from source
df = df[["open", "high", "low", "close", "volume"]].copy()
print(f"  bars: {len(df):,}  range: {df.index[0]} → {df.index[-1]}")

# Pip size for EURUSD (5-digit broker)
PIP = 0.0001

# ──────────────────────────────────────────────────────────────────
# Standard indicators (no TA-Lib dependency — same math, pandas/numpy)
# ──────────────────────────────────────────────────────────────────

def ema(s, n):
    return s.ewm(span=n, adjust=False).mean()

def sma(s, n):
    return s.rolling(n).mean()

def rsi(close, n=14):
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1/n, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1/n, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - 100 / (1 + rs)

def atr(high, low, close, n=14):
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low  - close.shift()).abs()
    tr  = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.ewm(alpha=1/n, adjust=False).mean()

def macd(close, fast=12, slow=26, signal=9):
    line = ema(close, fast) - ema(close, slow)
    sig  = ema(line, signal)
    hist = line - sig
    return line, sig, hist

def bollinger(close, n=20, k=2):
    mid = sma(close, n)
    sd  = close.rolling(n).std(ddof=0)
    up, lo = mid + k*sd, mid - k*sd
    pctB = (close - lo) / (up - lo)
    width = (up - lo) / mid
    return mid, up, lo, pctB, width

def stoch(high, low, close, k_period=14, k_smooth=3, d_smooth=3):
    ll = low.rolling(k_period).min()
    hh = high.rolling(k_period).max()
    raw_k = 100 * (close - ll) / (hh - ll)
    k = raw_k.rolling(k_smooth).mean()
    d = k.rolling(d_smooth).mean()
    return k, d

def adx(high, low, close, n=14):
    up   = high.diff()
    dn   = -low.diff()
    plus_dm  = ((up > dn) & (up > 0)).astype(float) * up
    minus_dm = ((dn > up) & (dn > 0)).astype(float) * dn
    tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
    atr_ = tr.ewm(alpha=1/n, adjust=False).mean()
    plus_di  = 100 * plus_dm.ewm(alpha=1/n, adjust=False).mean()  / atr_
    minus_di = 100 * minus_dm.ewm(alpha=1/n, adjust=False).mean() / atr_
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx_ = dx.ewm(alpha=1/n, adjust=False).mean()
    return adx_, plus_di, minus_di

# ──────────────────────────────────────────────────────────────────
# Compute everything
# ──────────────────────────────────────────────────────────────────
print("computing indicators...")
o, h, l, c, v = df["open"], df["high"], df["low"], df["close"], df["volume"]

# Trend / position
df["ema20"]  = ema(c, 20)
df["ema50"]  = ema(c, 50)
df["ema200"] = ema(c, 200)
df["dist_ema20_pips"]  = (c - df["ema20"])  / PIP
df["dist_ema50_pips"]  = (c - df["ema50"])  / PIP
df["dist_ema200_pips"] = (c - df["ema200"]) / PIP

# Oscillators
df["rsi14"] = rsi(c, 14)
k, d = stoch(h, l, c)
df["stoch_k"], df["stoch_d"] = k, d
mline, msig, mhist = macd(c)
df["macd"], df["macd_sig"], df["macd_hist"] = mline, msig, mhist

# Volatility / bands
df["atr14_pips"] = atr(h, l, c, 14) / PIP
mid, up, lo, pctB, width = bollinger(c)
df["bb_pctB"], df["bb_width_pips"] = pctB, (up - lo) / PIP

# Trend strength
adx_, pdi, ndi = adx(h, l, c, 14)
df["adx14"] = adx_
df["plus_di"] = pdi
df["minus_di"] = ndi

# Momentum
df["mom10_pips"] = (c - c.shift(10)) / PIP
df["roc10_pct"]  = 100 * (c / c.shift(10) - 1)

# Candle anatomy (size-aware)
body  = (c - o)
rng   = (h - l).replace(0, np.nan)
upper_wick = h - np.maximum(o, c)
lower_wick = np.minimum(o, c) - l
df["body_pips"]        = body / PIP
df["range_pips"]       = (h - l) / PIP
df["body_to_range"]    = body / rng                # +1=full bull body, -1=full bear, ~0=doji
df["upper_wick_ratio"] = upper_wick / rng
df["lower_wick_ratio"] = lower_wick / rng
df["is_doji"]          = ((body.abs() / rng) < 0.1).astype(int)
df["is_pin_bull"]      = ((df["lower_wick_ratio"] > 0.55) & (df["body_to_range"] > 0)).astype(int)
df["is_pin_bear"]      = ((df["upper_wick_ratio"] > 0.55) & (df["body_to_range"] < 0)).astype(int)

# Engulfing (vs previous bar)
prev_body = body.shift()
df["is_eng_bull"] = ((body > 0) & (prev_body < 0) & (c > o.shift()) & (o < c.shift())).astype(int)
df["is_eng_bear"] = ((body < 0) & (prev_body > 0) & (c < o.shift()) & (o > c.shift())).astype(int)

# Volume
df["vol_z20"] = (v - v.rolling(20).mean()) / v.rolling(20).std(ddof=0)
df["vol_relvar20"] = v / v.rolling(20).mean()

# Time-of-day (UTC hour) — sessions matter per saved EA Design Rules
df["hour_utc"] = df.index.hour
df["dow"]      = df.index.dayofweek   # 0=Mon

# Drop warm-up rows
df_clean = df.dropna(subset=["ema200", "adx14", "rsi14"]).copy()
print(f"  after warm-up trim: {len(df_clean):,} bars")

# Save
df_clean.to_csv(OUT, compression="gzip", float_format="%.6f")
print(f"saved → {OUT}  ({len(df_clean.columns)} cols)")
print(f"sample columns: {list(df_clean.columns[-15:])}")
