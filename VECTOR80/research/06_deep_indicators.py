"""
Step 6 — Deep indicator pass: volatility regime, exhaustion, proximity.

Goal: build a feature set rich enough that a combination of them forms a
distinguishable 'profile' for good pivots.

Categories added on top of step 1:

VOLATILITY
  atr5 / atr14 / atr50            — multi-scale ATR
  atr_ratio_5_50                   — short vs long ATR  (expansion)
  atr_pct100                       — rank of atr14 in last 100 bars
  realized_vol_20                  — rolling stdev of returns
  range_z20                        — current bar range as z-score of last 20
  range_expansion_5                — current range / mean(range, 5)
  bb_squeeze                       — bb_width / its 50-bar avg  (low = squeeze)
  keltner_pos                      — close position vs Keltner channels
  vol_of_vol_20                    — stdev of atr14 over 20 bars

EXHAUSTION
  consec_up / consec_dn            — streak length in current direction
  velocity_3                       — close - close.shift(3)
  acceleration                     — velocity.diff()
  range_climax                     — range > 2 × mean(range,20)
  vol_climax                       — vol_z20 > 2
  dist_ema20_atr                   — distance from EMA20 in ATR units
  dist_ema50_atr
  bb_outside                       — close outside BB band
  williams_r14                     — Williams %R
  consec_above_ema20 / below_ema20
  rsi_overbought / rsi_oversold    — RSI > 70 / < 30 flag
  rsi_div_bear / rsi_div_bull      — simple swing divergence vs N-bar lookback
  macd_div_bear / macd_div_bull

PROXIMITY
  pips_to_round_50                 — distance to nearest 0.0050 level
  pips_to_round_100                — distance to nearest 0.0100 level
  dist_to_5bar_high_pips / low     — recent extremes
  dist_to_20bar_high_pips / low
  dist_to_50bar_high_pips / low
  dist_to_session_open_pips        — open of London/NY/Asian session
  dist_to_prev_day_high_pips
  dist_to_prev_day_low_pips
  prev_day_in_range                — flag if price between prev day H/L
"""

import pandas as pd
import numpy as np

SRC = "/home/cmake/Vector/research/m5_with_indicators.csv.gz"
OUT = "/home/cmake/Vector/research/m5_deep.csv.gz"
PIP = 0.0001

print("loading...")
df = pd.read_csv(SRC, index_col=0, parse_dates=True)
print(f"  {len(df):,} bars")

o, h, l, c = df["open"], df["high"], df["low"], df["close"]


# ── helpers ──────────────────────────────────────────────────────
def true_range(h, l, c):
    tr1 = h - l
    tr2 = (h - c.shift()).abs()
    tr3 = (l - c.shift()).abs()
    return pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

def atr(h, l, c, n):
    return true_range(h, l, c).ewm(alpha=1/n, adjust=False).mean()

def rolling_rank_pct(s, n):
    return s.rolling(n).apply(lambda x: (x <= x[-1]).sum() / len(x), raw=False)


# ── VOLATILITY ───────────────────────────────────────────────────
print("volatility features...")
df["atr5"]   = atr(h, l, c, 5)  / PIP
df["atr50"]  = atr(h, l, c, 50) / PIP
df["atr_ratio_5_50"] = df["atr5"] / df["atr50"].replace(0, np.nan)
df["atr_pct100"] = df["atr14_pips"].rolling(100).rank(pct=True)
ret = c.pct_change()
df["realized_vol_20"] = ret.rolling(20).std() * 1e4   # bps-like scale
df["range_z20"] = (df["range_pips"] - df["range_pips"].rolling(20).mean()) \
                   / df["range_pips"].rolling(20).std()
df["range_expansion_5"] = df["range_pips"] / df["range_pips"].rolling(5).mean()
df["bb_squeeze"] = df["bb_width_pips"] / df["bb_width_pips"].rolling(50).mean()

# Keltner (ema20 ± 2*ATR)
df["keltner_upper"] = df["ema20"] + 2 * df["atr14_pips"] * PIP
df["keltner_lower"] = df["ema20"] - 2 * df["atr14_pips"] * PIP
df["keltner_pos"]   = (c - df["keltner_lower"]) / (df["keltner_upper"] - df["keltner_lower"])

df["vol_of_vol_20"] = df["atr14_pips"].rolling(20).std()


# ── EXHAUSTION ──────────────────────────────────────────────────
print("exhaustion features...")
bull = (c > o).astype(int)
bear = (c < o).astype(int)
# streak: cumulative consecutive same-direction bars
def streak(s):
    grp = (s != s.shift()).cumsum()
    return s.groupby(grp).cumsum()
df["consec_up"] = streak(bull) * bull
df["consec_dn"] = streak(bear) * bear

df["velocity_3"]  = c - c.shift(3)
df["accel"]       = df["velocity_3"].diff()

df["range_climax"] = (df["range_pips"] > 2 * df["range_pips"].rolling(20).mean()).astype(int)
df["vol_climax"]   = (df["vol_z20"] > 2.0).astype(int)

# Overextension in ATR units
df["dist_ema20_atr"] = (c - df["ema20"]) / (df["atr14_pips"] * PIP).replace(0, np.nan)
df["dist_ema50_atr"] = (c - df["ema50"]) / (df["atr14_pips"] * PIP).replace(0, np.nan)

# BB breach
bb_mid = c.rolling(20).mean()
bb_std = c.rolling(20).std(ddof=0)
bb_up  = bb_mid + 2*bb_std
bb_lo  = bb_mid - 2*bb_std
df["bb_breach_up"] = (c > bb_up).astype(int)
df["bb_breach_dn"] = (c < bb_lo).astype(int)

# Williams %R(14)
ll14 = l.rolling(14).min()
hh14 = h.rolling(14).max()
df["williams_r14"] = -100 * (hh14 - c) / (hh14 - ll14).replace(0, np.nan)

# Consec above/below EMA20
above = (c > df["ema20"]).astype(int)
below = (c < df["ema20"]).astype(int)
df["consec_above_ema20"] = streak(above) * above
df["consec_below_ema20"] = streak(below) * below

df["rsi_overbought"] = (df["rsi14"] > 70).astype(int)
df["rsi_oversold"]   = (df["rsi14"] < 30).astype(int)

# Simple divergence: price HH vs RSI lower-high (in 20-bar window)
N = 20
price_hh_now = h == h.rolling(N).max()
price_ll_now = l == l.rolling(N).min()
rsi_lower_high = df["rsi14"] < df["rsi14"].rolling(N).max()
rsi_higher_low = df["rsi14"] > df["rsi14"].rolling(N).min()
df["rsi_div_bear"] = (price_hh_now & rsi_lower_high).astype(int)
df["rsi_div_bull"] = (price_ll_now & rsi_higher_low).astype(int)

macd_lower_high = df["macd"] < df["macd"].rolling(N).max()
macd_higher_low = df["macd"] > df["macd"].rolling(N).min()
df["macd_div_bear"] = (price_hh_now & macd_lower_high).astype(int)
df["macd_div_bull"] = (price_ll_now & macd_higher_low).astype(int)


# ── PROXIMITY ───────────────────────────────────────────────────
print("proximity features...")
# Round numbers
df["pips_to_round_50"]  = (np.minimum(c - np.floor(c*200)/200,
                                       np.ceil(c*200)/200 - c)) / PIP
df["pips_to_round_100"] = (np.minimum(c - np.floor(c*100)/100,
                                       np.ceil(c*100)/100 - c)) / PIP

# Recent N-bar extremes
for N in [5, 20, 50]:
    hi = h.rolling(N).max()
    lo = l.rolling(N).min()
    df[f"dist_to_{N}bar_high_pips"] = (hi - c) / PIP
    df[f"dist_to_{N}bar_low_pips"]  = (c - lo) / PIP

# Previous day H/L and current session high/low
df["date"] = df.index.normalize()
day_h = df.groupby("date")["high"].cummax()
day_l = df.groupby("date")["low"].cummin()
df["dist_to_today_high_pips"] = (day_h - c) / PIP
df["dist_to_today_low_pips"]  = (c - day_l) / PIP

# Previous day H/L
daily = df.groupby("date").agg(prev_h=("high", "max"), prev_l=("low", "min"))
daily["prev_h_shift"] = daily["prev_h"].shift()
daily["prev_l_shift"] = daily["prev_l"].shift()
df = df.merge(daily[["prev_h_shift", "prev_l_shift"]],
              left_on="date", right_index=True, how="left")
df["dist_to_prev_day_high_pips"] = (df["prev_h_shift"] - c) / PIP
df["dist_to_prev_day_low_pips"]  = (c - df["prev_l_shift"]) / PIP
df["in_prev_day_range"] = ((c <= df["prev_h_shift"]) & (c >= df["prev_l_shift"])).astype(int)

df = df.drop(columns=["date", "prev_h_shift", "prev_l_shift",
                       "keltner_upper", "keltner_lower"], errors="ignore")

# Drop warm-up rows again (we now need 100 bars for ATR percentile, 50 for Keltner)
df_clean = df.dropna(subset=["atr_pct100", "bb_squeeze", "dist_to_50bar_high_pips"]).copy()
print(f"\n  after warm-up trim: {len(df_clean):,} bars")

print(f"  total feature cols: {len(df_clean.columns)}")
new_cols = [c for c in df_clean.columns if c not in pd.read_csv(SRC, index_col=0, nrows=0).columns]
print(f"  NEW columns added ({len(new_cols)}):")
for nc in new_cols:
    print(f"    {nc}")

df_clean.to_csv(OUT, compression="gzip", float_format="%.6f")
print(f"\nsaved → {OUT}")
