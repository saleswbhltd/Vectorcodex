"""
Step 35 — Build the COMPLETE per-bar panel: Dukascopy M5 indicators + tick features + H1 HTF.
Output is the input to the final per-type classifier.
"""

import pandas as pd
import numpy as np

M5_TICK_FEATS = "/home/cmake/Vector/research/EURUSD_M5_tick_features.csv.gz"
H1_SRC        = "/mnt/c/Users/cmake/Documents/MarketData/EURUSD/EURUSD_H1_20250101_20260601.csv"
OUT           = "/home/cmake/Vector/research/EURUSD_M5_FULL_PANEL.csv.gz"
PIP           = 0.0001


def add_m5_indicators(df):
    """Standard indicator panel (same as step 6)."""
    o, h, l, c = df["open"], df["high"], df["low"], df["close"]
    v = df.get("tick_volume", df.get("volume", pd.Series(1, index=df.index)))

    def ema(s, n): return s.ewm(span=n, adjust=False).mean()
    def true_range(h, l, c):
        return pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    def atr(h, l, c, n): return true_range(h, l, c).ewm(alpha=1/n, adjust=False).mean()
    def rsi(c, n=14):
        d = c.diff()
        g = d.clip(lower=0).ewm(alpha=1/n, adjust=False).mean()
        loss = (-d.clip(upper=0)).ewm(alpha=1/n, adjust=False).mean()
        return 100 - 100 / (1 + g / loss.replace(0, np.nan))
    def stoch(h, l, c, kp=14, ks=3, ds=3):
        ll = l.rolling(kp).min(); hh = h.rolling(kp).max()
        rk = 100*(c-ll)/(hh-ll).replace(0, np.nan)
        k = rk.rolling(ks).mean(); d = k.rolling(ds).mean()
        return k, d
    def adx(h, l, c, n=14):
        up, dn = h.diff(), -l.diff()
        plus_dm  = ((up > dn) & (up > 0)).astype(float) * up
        minus_dm = ((dn > up) & (dn > 0)).astype(float) * dn
        atr_ = true_range(h, l, c).ewm(alpha=1/n, adjust=False).mean()
        pdi = 100*plus_dm.ewm(alpha=1/n, adjust=False).mean()/atr_
        ndi = 100*minus_dm.ewm(alpha=1/n, adjust=False).mean()/atr_
        dx  = 100*(pdi - ndi).abs() / (pdi + ndi).replace(0, np.nan)
        return dx.ewm(alpha=1/n, adjust=False).mean(), pdi, ndi

    df["ema20"] = ema(c, 20)
    df["ema50"] = ema(c, 50)
    df["ema200"] = ema(c, 200)
    df["rsi14"] = rsi(c, 14)
    k, d = stoch(h, l, c); df["stoch_k"], df["stoch_d"] = k, d
    df["macd"] = ema(c, 12) - ema(c, 26)
    df["macd_sig"] = ema(df["macd"], 9)
    df["macd_hist"] = df["macd"] - df["macd_sig"]
    df["atr5"] = atr(h, l, c, 5) / PIP
    df["atr14_pips"] = atr(h, l, c, 14) / PIP
    df["atr50"] = atr(h, l, c, 50) / PIP
    df["atr_ratio_5_50"] = df["atr5"] / df["atr50"].replace(0, np.nan)
    df["atr_pct100"] = df["atr14_pips"].rolling(100).rank(pct=True)
    mid = c.rolling(20).mean(); sd = c.rolling(20).std(ddof=0)
    up, lo = mid + 2*sd, mid - 2*sd
    df["bb_pctB"] = (c - lo) / (up - lo)
    df["bb_width_pips"] = (up - lo) / PIP
    df["bb_squeeze"] = df["bb_width_pips"] / df["bb_width_pips"].rolling(50).mean()
    df["realized_vol_20"] = c.pct_change().rolling(20).std() * 1e4
    df["range_pips"] = (h - l) / PIP
    df["body_pips"] = (c - o) / PIP
    df["range_z20"] = (df["range_pips"] - df["range_pips"].rolling(20).mean()) / df["range_pips"].rolling(20).std()
    body = (c - o); rng = (h - l).replace(0, np.nan)
    df["body_to_range"] = body / rng
    df["upper_wick_ratio"] = (h - np.maximum(o, c)) / rng
    df["lower_wick_ratio"] = (np.minimum(o, c) - l) / rng
    df["vol_z20"] = (v - v.rolling(20).mean()) / v.rolling(20).std(ddof=0)
    df["vol_of_vol_20"] = df["atr14_pips"].rolling(20).std()
    bull = (c > o).astype(int); bear = (c < o).astype(int)
    def streak(s):
        grp = (s != s.shift()).cumsum()
        return s.groupby(grp).cumsum()
    df["consec_up"] = streak(bull) * bull
    df["consec_dn"] = streak(bear) * bear
    df["velocity_3"] = c - c.shift(3)
    df["accel"] = df["velocity_3"].diff()
    df["dist_ema20_atr"] = (c - df["ema20"]) / (df["atr14_pips"] * PIP).replace(0, np.nan)
    df["dist_ema50_atr"] = (c - df["ema50"]) / (df["atr14_pips"] * PIP).replace(0, np.nan)
    hh14 = h.rolling(14).max(); ll14 = l.rolling(14).min()
    df["williams_r14"] = -100 * (hh14 - c) / (hh14 - ll14).replace(0, np.nan)
    df["adx14"], df["plus_di"], df["minus_di"] = adx(h, l, c, 14)
    for N in [5, 20, 50]:
        df[f"dist_to_{N}bar_high_pips"] = (h.rolling(N).max() - c) / PIP
        df[f"dist_to_{N}bar_low_pips"]  = (c - l.rolling(N).min()) / PIP
    df["date"] = df.index.normalize()
    df["dist_to_today_high_pips"] = (df.groupby("date")["high"].cummax() - c) / PIP
    df["dist_to_today_low_pips"]  = (c - df.groupby("date")["low"].cummin()) / PIP
    df = df.drop(columns=["date"])
    df["hour_utc"] = df.index.hour
    df["dow"] = df.index.dayofweek
    return df


def add_h1_features(df, h1_path):
    h1 = pd.read_csv(h1_path)
    h1["datetime"] = pd.to_datetime(h1["datetime"], utc=True).dt.tz_localize(None)
    h1 = h1.set_index("datetime").sort_index()
    h1 = h1[~h1.index.duplicated(keep="first")]
    o, h, l, c = h1["open"], h1["high"], h1["low"], h1["close"]
    def ema(s, n): return s.ewm(span=n, adjust=False).mean()
    def rsi(c, n=14):
        d = c.diff()
        g = d.clip(lower=0).ewm(alpha=1/n, adjust=False).mean()
        ls = (-d.clip(upper=0)).ewm(alpha=1/n, adjust=False).mean()
        return 100 - 100 / (1 + g/ls.replace(0, np.nan))
    def atr(h, l, c, n=14):
        tr = pd.concat([h-l, (h-c.shift()).abs(), (l-c.shift()).abs()], axis=1).max(axis=1)
        return tr.ewm(alpha=1/n, adjust=False).mean()
    h1["h1_rsi14"] = rsi(c, 14)
    h1["h1_ema50"] = ema(c, 50); h1["h1_ema200"] = ema(c, 200)
    h1["h1_atr14_pips"] = atr(h, l, c, 14) / PIP
    h1["h1_ema50_slope_pips"]  = (h1["h1_ema50"]  - h1["h1_ema50"].shift(24)) / PIP
    h1["h1_ema200_slope_pips"] = (h1["h1_ema200"] - h1["h1_ema200"].shift(24)) / PIP
    h1["h1_dist_ema50_pips"]  = (c - h1["h1_ema50"]) / PIP
    h1["h1_dist_ema200_pips"] = (c - h1["h1_ema200"]) / PIP
    h1["h1_above_ema50"]  = (c > h1["h1_ema50"]).astype(int)
    h1["h1_above_ema200"] = (c > h1["h1_ema200"]).astype(int)
    mid = c.rolling(20).mean(); sd = c.rolling(20).std(ddof=0)
    h1["h1_bb_pctB"] = (c - (mid - 2*sd)) / ((mid + 2*sd) - (mid - 2*sd))
    u50 = h1["h1_ema50_slope_pips"] > 0; u200 = h1["h1_ema200_slope_pips"] > 0
    h1["h1_trend_dir"] = np.where(u50 & u200, 1, np.where(~u50 & ~u200, -1, 0))
    h1["h1_dist_24h_high_pips"] = (h.rolling(24).max() - c) / PIP
    h1["h1_dist_24h_low_pips"]  = (c - l.rolling(24).min()) / PIP
    h1_keep = [
        "h1_rsi14", "h1_atr14_pips",
        "h1_ema50_slope_pips", "h1_ema200_slope_pips",
        "h1_dist_ema50_pips", "h1_dist_ema200_pips",
        "h1_above_ema50", "h1_above_ema200",
        "h1_bb_pctB", "h1_trend_dir",
        "h1_dist_24h_high_pips", "h1_dist_24h_low_pips",
    ]
    h1_f = h1[h1_keep].dropna(subset=["h1_ema50_slope_pips"])
    # Merge backward — M5 bar at time t uses last H1 ≤ t
    merged = pd.merge_asof(
        df.reset_index().sort_values("datetime"),
        h1_f.reset_index().sort_values("datetime"),
        on="datetime", direction="backward"
    ).set_index("datetime")
    return merged


def main():
    print("loading M5 + tick features...")
    df = pd.read_csv(M5_TICK_FEATS, parse_dates=["datetime"]).set_index("datetime")
    print(f"  bars: {len(df):,}  cols: {len(df.columns)}")

    print("computing M5 indicator panel...")
    df = add_m5_indicators(df)

    print("attaching H1 features...")
    df = add_h1_features(df, H1_SRC)

    df = df.dropna(subset=["atr14_pips", "bb_pctB", "h1_rsi14"])
    print(f"\nFinal panel: {len(df):,} bars × {len(df.columns)} cols")
    df.to_csv(OUT, compression="gzip", float_format="%.6f")
    print(f"saved → {OUT}")


if __name__ == "__main__":
    main()
