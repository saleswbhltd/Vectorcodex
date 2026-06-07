"""
Step 20 — Process 2026 EURUSD M5/M1 data through the same indicator pipeline.

Inputs: EURUSD_M5.csv, EURUSD_M1.csv from MT5 export
Outputs:
  m5_2026_deep.csv.gz
  m1_2026_deep.csv.gz
"""

import pandas as pd
import numpy as np

M5_SRC = "/mnt/c/Users/cmake/AppData/Roaming/MetaQuotes/Terminal/5FFA568149E88FCD5B44D926DCFEAA79/MQL5/Files/EURUSD_M5.csv"
M1_SRC = "/mnt/c/Users/cmake/AppData/Roaming/MetaQuotes/Terminal/5FFA568149E88FCD5B44D926DCFEAA79/MQL5/Files/EURUSD_M1.csv"
M5_OUT = "/home/cmake/Vector/research/m5_2026_deep.csv.gz"
M1_OUT = "/home/cmake/Vector/research/m1_2026_deep.csv.gz"
PIP = 0.0001


def compute_full(df):
    """Apply the same 73-feature pipeline as step 6."""
    df = df.copy()
    o, h, l, c = df["open"], df["high"], df["low"], df["close"]
    v = df.get("tick_volume", df.get("volume", pd.Series(1, index=df.index)))

    def ema(s, n): return s.ewm(span=n, adjust=False).mean()
    def sma(s, n): return s.rolling(n).mean()

    def rsi(close, n=14):
        d = close.diff()
        gain = d.clip(lower=0).ewm(alpha=1/n, adjust=False).mean()
        loss = (-d.clip(upper=0)).ewm(alpha=1/n, adjust=False).mean()
        rs = gain / loss.replace(0, np.nan)
        return 100 - 100 / (1 + rs)

    def true_range(h, l, c):
        return pd.concat([h-l, (h-c.shift()).abs(), (l-c.shift()).abs()], axis=1).max(axis=1)

    def atr(h, l, c, n):
        return true_range(h, l, c).ewm(alpha=1/n, adjust=False).mean()

    def stoch(h, l, c, kp=14, ks=3, ds=3):
        ll = l.rolling(kp).min(); hh = h.rolling(kp).max()
        rk = 100*(c-ll)/(hh-ll).replace(0, np.nan)
        k = rk.rolling(ks).mean(); d = k.rolling(ds).mean()
        return k, d

    def adx(h, l, c, n=14):
        up = h.diff(); dn = -l.diff()
        plus_dm = ((up > dn) & (up > 0)).astype(float) * up
        minus_dm = ((dn > up) & (dn > 0)).astype(float) * dn
        tr = true_range(h, l, c)
        atr_ = tr.ewm(alpha=1/n, adjust=False).mean()
        plus_di = 100*plus_dm.ewm(alpha=1/n, adjust=False).mean()/atr_
        minus_di = 100*minus_dm.ewm(alpha=1/n, adjust=False).mean()/atr_
        dx = 100*(plus_di-minus_di).abs()/(plus_di+minus_di).replace(0, np.nan)
        return dx.ewm(alpha=1/n, adjust=False).mean(), plus_di, minus_di

    # Step 1 base features
    df["ema20"] = ema(c, 20)
    df["ema50"] = ema(c, 50)
    df["ema200"] = ema(c, 200)
    df["dist_ema20_pips"] = (c - df["ema20"]) / PIP
    df["dist_ema50_pips"] = (c - df["ema50"]) / PIP
    df["dist_ema200_pips"] = (c - df["ema200"]) / PIP
    df["rsi14"] = rsi(c, 14)
    k, d = stoch(h, l, c); df["stoch_k"], df["stoch_d"] = k, d
    line = ema(c, 12) - ema(c, 26); sig = ema(line, 9)
    df["macd"], df["macd_sig"], df["macd_hist"] = line, sig, line - sig
    df["atr14_pips"] = atr(h, l, c, 14) / PIP
    mid = sma(c, 20); sd = c.rolling(20).std(ddof=0)
    up, lo = mid + 2*sd, mid - 2*sd
    df["bb_pctB"] = (c-lo)/(up-lo); df["bb_width_pips"] = (up-lo)/PIP
    adx_, pdi, ndi = adx(h, l, c, 14)
    df["adx14"], df["plus_di"], df["minus_di"] = adx_, pdi, ndi
    df["mom10_pips"] = (c - c.shift(10))/PIP
    df["roc10_pct"] = 100*(c/c.shift(10) - 1)
    body = (c - o); rng = (h - l).replace(0, np.nan)
    df["body_pips"] = body/PIP; df["range_pips"] = (h-l)/PIP
    df["body_to_range"] = body/rng
    df["upper_wick_ratio"] = (h - np.maximum(o, c))/rng
    df["lower_wick_ratio"] = (np.minimum(o, c) - l)/rng
    df["is_doji"] = ((body.abs()/rng) < 0.1).astype(int)
    df["is_pin_bull"] = ((df["lower_wick_ratio"] > 0.55) & (df["body_to_range"] > 0)).astype(int)
    df["is_pin_bear"] = ((df["upper_wick_ratio"] > 0.55) & (df["body_to_range"] < 0)).astype(int)
    pb = body.shift()
    df["is_eng_bull"] = ((body > 0) & (pb < 0) & (c > o.shift()) & (o < c.shift())).astype(int)
    df["is_eng_bear"] = ((body < 0) & (pb > 0) & (c < o.shift()) & (o > c.shift())).astype(int)
    df["vol_z20"] = (v - v.rolling(20).mean())/v.rolling(20).std(ddof=0)
    df["vol_relvar20"] = v/v.rolling(20).mean()
    df["hour_utc"] = df.index.hour
    df["dow"] = df.index.dayofweek

    # Step 6 deep features
    df["atr5"] = atr(h, l, c, 5) / PIP
    df["atr50"] = atr(h, l, c, 50) / PIP
    df["atr_ratio_5_50"] = df["atr5"] / df["atr50"].replace(0, np.nan)
    df["atr_pct100"] = df["atr14_pips"].rolling(100).rank(pct=True)
    ret = c.pct_change()
    df["realized_vol_20"] = ret.rolling(20).std() * 1e4
    df["range_z20"] = (df["range_pips"] - df["range_pips"].rolling(20).mean()) / df["range_pips"].rolling(20).std()
    df["range_expansion_5"] = df["range_pips"] / df["range_pips"].rolling(5).mean()
    df["bb_squeeze"] = df["bb_width_pips"] / df["bb_width_pips"].rolling(50).mean()
    df["keltner_pos"] = (c - (df["ema20"] - 2*df["atr14_pips"]*PIP)) / (4*df["atr14_pips"]*PIP)
    df["vol_of_vol_20"] = df["atr14_pips"].rolling(20).std()

    bull = (c > o).astype(int); bear = (c < o).astype(int)
    def streak(s):
        grp = (s != s.shift()).cumsum()
        return s.groupby(grp).cumsum()
    df["consec_up"] = streak(bull) * bull
    df["consec_dn"] = streak(bear) * bear
    df["velocity_3"] = c - c.shift(3)
    df["accel"] = df["velocity_3"].diff()
    df["range_climax"] = (df["range_pips"] > 2 * df["range_pips"].rolling(20).mean()).astype(int)
    df["vol_climax"] = (df["vol_z20"] > 2.0).astype(int)
    df["dist_ema20_atr"] = (c - df["ema20"]) / (df["atr14_pips"] * PIP).replace(0, np.nan)
    df["dist_ema50_atr"] = (c - df["ema50"]) / (df["atr14_pips"] * PIP).replace(0, np.nan)
    df["bb_breach_up"] = (c > up).astype(int)
    df["bb_breach_dn"] = (c < lo).astype(int)
    hh14 = h.rolling(14).max(); ll14 = l.rolling(14).min()
    df["williams_r14"] = -100*(hh14-c)/(hh14-ll14).replace(0, np.nan)
    above = (c > df["ema20"]).astype(int); below = (c < df["ema20"]).astype(int)
    df["consec_above_ema20"] = streak(above) * above
    df["consec_below_ema20"] = streak(below) * below
    df["rsi_overbought"] = (df["rsi14"] > 70).astype(int)
    df["rsi_oversold"] = (df["rsi14"] < 30).astype(int)

    N = 20
    p_hh = h == h.rolling(N).max(); p_ll = l == l.rolling(N).min()
    rsi_lh = df["rsi14"] < df["rsi14"].rolling(N).max()
    rsi_hl = df["rsi14"] > df["rsi14"].rolling(N).min()
    df["rsi_div_bear"] = (p_hh & rsi_lh).astype(int)
    df["rsi_div_bull"] = (p_ll & rsi_hl).astype(int)
    macd_lh = df["macd"] < df["macd"].rolling(N).max()
    macd_hl = df["macd"] > df["macd"].rolling(N).min()
    df["macd_div_bear"] = (p_hh & macd_lh).astype(int)
    df["macd_div_bull"] = (p_ll & macd_hl).astype(int)

    df["pips_to_round_50"] = (np.minimum(c - np.floor(c*200)/200, np.ceil(c*200)/200 - c))/PIP
    df["pips_to_round_100"] = (np.minimum(c - np.floor(c*100)/100, np.ceil(c*100)/100 - c))/PIP
    for N in [5, 20, 50]:
        hi = h.rolling(N).max(); lo_ = l.rolling(N).min()
        df[f"dist_to_{N}bar_high_pips"] = (hi - c)/PIP
        df[f"dist_to_{N}bar_low_pips"] = (c - lo_)/PIP
    df["date"] = df.index.normalize()
    day_h = df.groupby("date")["high"].cummax()
    day_l = df.groupby("date")["low"].cummin()
    df["dist_to_today_high_pips"] = (day_h - c)/PIP
    df["dist_to_today_low_pips"] = (c - day_l)/PIP
    daily = df.groupby("date").agg(prev_h=("high","max"), prev_l=("low","min"))
    daily["prev_h_shift"] = daily["prev_h"].shift()
    daily["prev_l_shift"] = daily["prev_l"].shift()
    df = df.merge(daily[["prev_h_shift","prev_l_shift"]], left_on="date", right_index=True, how="left")
    df["dist_to_prev_day_high_pips"] = (df["prev_h_shift"] - c)/PIP
    df["dist_to_prev_day_low_pips"] = (c - df["prev_l_shift"])/PIP
    df["in_prev_day_range"] = ((c <= df["prev_h_shift"]) & (c >= df["prev_l_shift"])).astype(int)
    df = df.drop(columns=["date","prev_h_shift","prev_l_shift"])
    return df


def process(src, out, label):
    print(f"\n── {label} ──")
    df = pd.read_csv(src)
    df["datetime"] = pd.to_datetime(df["datetime"], format="%Y.%m.%d %H:%M:%S")
    df = df.set_index("datetime").sort_index()
    print(f"  loaded {len(df):,} bars, range: {df.index[0]} → {df.index[-1]}")
    # Standardise column names
    if "tick_volume" not in df.columns and "volume" in df.columns:
        df = df.rename(columns={"volume": "tick_volume"})
    df = compute_full(df)
    df_clean = df.dropna(subset=["atr_pct100", "bb_squeeze", "dist_to_50bar_high_pips"])
    print(f"  after warm-up: {len(df_clean):,} bars, {len(df_clean.columns)} cols")
    df_clean.to_csv(out, compression="gzip", float_format="%.6f")
    print(f"  saved → {out}")


if __name__ == "__main__":
    process(M5_SRC, M5_OUT, "M5 2026")
    process(M1_SRC, M1_OUT, "M1 2026")
