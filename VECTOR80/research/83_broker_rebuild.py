"""
Step 83 — Rebuild the full pipeline using broker tick data.

The VECTOR003 GBMs were trained on Dukascopy tick data. Because the tick
microstructure features (bid_aggressor_pct, spread_avg, velocity, etc.) differ
between Dukascopy and the live broker (RoboForex ECN), the models misfired live.

This script replaces steps 34 + 35 using exported broker ticks, then re-runs
candidate generation (step 56) and GBM training (step 82) so the models are
calibrated to the broker's own tick distributions.

INPUT (from VECTOR_BrokerTickExport.mq5 run in MT5):
  Common\\Files\\BROKER_TICKS_EURUSD_20250201_20260605.csv
  Columns: datetime, time_msc, bid, ask, last, volume, flags, mid

KEY: broker timestamps are UTC+3 (server time).
     We convert to UTC so the panel aligns with the existing Dukascopy pivot map.

OUTPUTS:
  research/EURUSD_M5_BROKER_FULL_PANEL.csv.gz   — full 70-feature panel (UTC)
  models/gbm_<CLASS>.pkl                          — retrained per-class GBMs
  models/manifest.json                            — updated manifest
  research/stage1_thresholds.json                 — updated Stage 1 thresholds
"""

import pandas as pd
import numpy as np
import os, json, pickle, warnings
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score

warnings.filterwarnings("ignore")

# ── Paths ──────────────────────────────────────────────────────────────────────
BROKER_TICK_CSV = "/mnt/c/Users/cmake/AppData/Roaming/MetaQuotes/Terminal/Common/Files/BROKER_TICKS_EURUSD_20250201_20260605.csv"
PIVOT_MAP_DEV   = "/home/cmake/Vector/research/pivot_map_zzlines_v2.csv"
PIVOT_MAP_OOS   = "/home/cmake/Vector/research/pivot_map_zzlines_oos.csv"
SCAN_CSV        = "/home/cmake/Vector/research/indicator_scan_zzlines.csv"
PANEL_OUT       = "/home/cmake/Vector/research/EURUSD_M5_BROKER_FULL_PANEL.csv.gz"
CALIBRATED_PANEL= "/home/cmake/Vector/research/EURUSD_M5_CALIBRATED_PANEL.csv.gz"
CAND_DIR        = "/home/cmake/Vector/research"
MODEL_DIR       = "/home/cmake/Vector/models"
STAGE1_OUT      = "/home/cmake/Vector/research/stage1_thresholds.json"
PIP             = 0.0001
BROKER_UTC_OFFSET_H = 3   # RoboForex server = UTC+3

DEV_START, DEV_END = "2025-02-01", "2026-02-28"
OOS_START, OOS_END = "2026-03-01", "2026-06-05"

CLASSES = [
    "BULL_CONTINUATION_HIGH", "BEAR_TREND_BREAK_HIGH",
    "WEAK_HIGH_IN_UPTREND",   "SELL_PULLBACK_DOWNTREND",
    "BUY_PULLBACK_UPTREND",   "WEAK_LOW_IN_DOWNTREND",
    "BULL_TREND_BREAK_LOW",   "BEAR_CONTINUATION_LOW",
]
CLASS_TO_LABEL = {
    "BULL_CONTINUATION_HIGH": "HH", "BEAR_TREND_BREAK_HIGH": "HH",
    "WEAK_HIGH_IN_UPTREND":   "LH", "SELL_PULLBACK_DOWNTREND": "LH",
    "BUY_PULLBACK_UPTREND":   "HL", "WEAK_LOW_IN_DOWNTREND":   "HL",
    "BULL_TREND_BREAK_LOW":   "LL", "BEAR_CONTINUATION_LOW":   "LL",
}
LABEL_TO_SIDE = {"HH": "SELL", "LH": "SELL", "LL": "BUY", "HL": "BUY"}
NON_FEAT = {"candidate_time","target_class","y_in_class","y_tradeable",
            "open","high","low","close","volume","tick_volume",
            "bid_volume","ask_volume","ema20","ema50","ema200","bar_high","bar_low"}
OP_POINTS = {
    "BULL_TREND_BREAK_LOW":    (70, 5), "BEAR_TREND_BREAK_HIGH":   (80, 5),
    "BULL_CONTINUATION_HIGH":  (70, 5), "BEAR_CONTINUATION_LOW":   (70, 5),
    "BUY_PULLBACK_UPTREND":    (60, 5), "SELL_PULLBACK_DOWNTREND": (80, 3),
    "WEAK_HIGH_IN_UPTREND":    (70, 3), "WEAK_LOW_IN_DOWNTREND":   (80, 3),
}


# ══════════════════════════════════════════════════════════════════════════════
# STEP A — Load broker ticks, convert to UTC, resample to M5
# ══════════════════════════════════════════════════════════════════════════════
def load_broker_ticks():
    print(f"\n{'='*60}")
    print("STEP A: Load broker ticks and resample to M5 (UTC)")
    print(f"{'='*60}")
    if not os.path.exists(BROKER_TICK_CSV):
        raise FileNotFoundError(
            f"Broker tick export not found:\n  {BROKER_TICK_CSV}\n"
            "Run VECTOR_BrokerTickExport.mq5 in MT5 first.")

    print(f"  Loading: {BROKER_TICK_CSV}")
    ticks = pd.read_csv(BROKER_TICK_CSV, parse_dates=["datetime"])
    print(f"  Raw ticks: {len(ticks):,}")

    # Convert broker time → UTC
    ticks["datetime"] = ticks["datetime"] - pd.Timedelta(hours=BROKER_UTC_OFFSET_H)
    ticks = ticks.sort_values("datetime").reset_index(drop=True)
    print(f"  UTC range: {ticks.datetime.min()} → {ticks.datetime.max()}")

    # Compute mid
    mask_ba = (ticks["bid"] > 0) & (ticks["ask"] > 0)
    ticks["mid"] = np.where(mask_ba,
                            (ticks["bid"] + ticks["ask"]) / 2,
                            ticks.get("last", np.nan))
    ticks = ticks.set_index("datetime")
    return ticks


def ticks_to_m5_ohlc(ticks):
    """Resample tick data to M5 OHLC using mid price."""
    mid = ticks["mid"].dropna()
    m5 = mid.resample("5min").ohlc()
    m5.columns = ["open","high","low","close"]
    m5["tick_volume"] = ticks["mid"].resample("5min").count()
    m5 = m5.dropna(subset=["open","high","low","close"])
    print(f"  M5 bars: {len(m5):,}  ({m5.index.min()} → {m5.index.max()})")
    return m5


# ══════════════════════════════════════════════════════════════════════════════
# STEP B — Compute tick features per M5 bar (from broker ticks)
# Matches research/34_tick_features.py formulas exactly
# ══════════════════════════════════════════════════════════════════════════════
def compute_tick_features(ticks, m5):
    print(f"\n{'='*60}")
    print("STEP B: Compute tick features (broker data)")
    print(f"{'='*60}")

    # Tick-level derived quantities
    ticks = ticks.copy()
    ticks["spread_pips"]   = (ticks["ask"] - ticks["bid"]) / PIP
    ticks["bid_change"]    = ticks["bid"].diff()
    ticks["ask_change"]    = ticks["ask"].diff()
    ticks["bid_up"]        = (ticks["bid_change"] > 0).astype(int)
    ticks["ask_down"]      = (ticks["ask_change"] < 0).astype(int)
    ticks["mid_change"]    = ticks["mid"].diff().abs() / PIP
    ticks["time_delta_ms"] = ticks.index.to_series().diff().dt.total_seconds() * 1000
    ticks["bar_time"]      = ticks.index.floor("5min")

    print("  Grouping by M5 bar...")
    g = ticks.groupby("bar_time", sort=False)

    feats = pd.DataFrame(index=g.size().index)
    feats["tick_count"]              = g.size()
    feats["median_tick_interval_ms"] = g["time_delta_ms"].median()
    feats["max_tick_interval_ms"]    = g["time_delta_ms"].max()
    feats["spread_avg"]              = g["spread_pips"].mean()
    feats["spread_max"]              = g["spread_pips"].max()
    feats["bid_aggressor_pct"]       = 100 * g["bid_up"].mean()
    feats["ask_aggressor_pct"]       = 100 * g["ask_down"].mean()
    feats["imbalance"]               = feats["bid_aggressor_pct"] - feats["ask_aggressor_pct"]

    def half_split(group):
        n = len(group)
        if n < 4:
            return pd.Series({"vel1":np.nan,"vel2":np.nan,"run_up":np.nan,
                               "run_dn":np.nan,"at_high_pct":np.nan,"at_low_pct":np.nan})
        half = n // 2
        v1 = group["mid_change"].iloc[:half].sum() / half
        v2 = group["mid_change"].iloc[half:].sum() / (n - half)
        mid = group["mid"].values
        cummax = np.maximum.accumulate(mid)
        cummin = np.minimum.accumulate(mid)
        run_up = float(np.max((cummax - mid[0]) / PIP))
        run_dn = float(np.max((mid[0] - cummin) / PIP))
        h = group["mid"].max(); l = group["mid"].min()
        at_h = ((h - group["mid"]) / PIP <= 1.0).mean() * 100
        at_l = ((group["mid"] - l) / PIP <= 1.0).mean() * 100
        return pd.Series({"vel1":v1,"vel2":v2,"run_up":run_up,
                          "run_dn":run_dn,"at_high_pct":at_h,"at_low_pct":at_l})

    print("  Per-bar velocity profile...")
    vdf = g.apply(half_split, include_groups=False)
    feats["tick_velocity_first_half"]  = vdf["vel1"]
    feats["tick_velocity_second_half"] = vdf["vel2"]
    feats["vel_ratio_2nd_to_1st"]      = vdf["vel2"] / vdf["vel1"].replace(0, np.nan)
    feats["max_run_up_pips_intrabar"]  = vdf["run_up"]
    feats["max_run_dn_pips_intrabar"]  = vdf["run_dn"]
    feats["ticks_at_high_pct"]         = vdf["at_high_pct"]
    feats["ticks_at_low_pct"]          = vdf["at_low_pct"]

    out = m5.join(feats, how="left")
    print(f"  Tick features computed: {feats.shape[1]} cols, {len(out):,} bars")
    return out


# ══════════════════════════════════════════════════════════════════════════════
# STEP C — Add OHLC indicators + H1 features (matches script 35)
# ══════════════════════════════════════════════════════════════════════════════
def ema(s, n): return s.ewm(span=n, adjust=False).mean()
def rsi(c, n=14):
    d = c.diff(); g2 = d.clip(lower=0).ewm(alpha=1/n,adjust=False).mean()
    ls = (-d.clip(upper=0)).ewm(alpha=1/n,adjust=False).mean()
    return 100 - 100/(1 + g2/ls.replace(0,np.nan))
def stoch(h,l,c,k=14,d=3):
    hh=h.rolling(k).max(); ll=l.rolling(k).min()
    k_=100*(c-ll)/(hh-ll).replace(0,np.nan); return k_, k_.rolling(d).mean()
def atr(h,l,c,n=14):
    tr = pd.concat([h-l,(h-c.shift()).abs(),(l-c.shift()).abs()],axis=1).max(axis=1)
    return tr.ewm(alpha=1/n,adjust=False).mean()
def adx(h,l,c,n=14):
    up=h.diff(); dn=-l.diff()
    plus_dm=up.where((up>dn)&(up>0),0); minus_dm=dn.where((dn>up)&(dn>0),0)
    atr_=atr(h,l,c,n); pdi=100*plus_dm.ewm(alpha=1/n,adjust=False).mean()/atr_
    ndi=100*minus_dm.ewm(alpha=1/n,adjust=False).mean()/atr_
    dx=100*(pdi-ndi).abs()/(pdi+ndi).replace(0,np.nan)
    return dx.ewm(alpha=1/n,adjust=False).mean(), pdi, ndi
def streak(s):
    grp=(s!=s.shift()).cumsum(); return s.groupby(grp).cumsum()

def add_ohlc_indicators(df):
    o=df["open"]; h=df["high"]; l=df["low"]; c=df["close"]; v=df["tick_volume"]
    df["ema20"]=ema(c,20); df["ema50"]=ema(c,50); df["ema200"]=ema(c,200)
    df["rsi14"]=rsi(c,14)
    df["stoch_k"],df["stoch_d"]=stoch(h,l,c)
    df["macd"]=ema(c,12)-ema(c,26); df["macd_sig"]=ema(df["macd"],9)
    df["macd_hist"]=df["macd"]-df["macd_sig"]
    df["atr5"]=atr(h,l,c,5)/PIP; df["atr14_pips"]=atr(h,l,c,14)/PIP
    df["atr50"]=atr(h,l,c,50)/PIP
    df["atr_ratio_5_50"]=df["atr5"]/df["atr50"].replace(0,np.nan)
    df["atr_pct100"]=df["atr14_pips"].rolling(100).rank(pct=True)
    mid2=c.rolling(20).mean(); sd=c.rolling(20).std(ddof=0)
    up,lo=mid2+2*sd, mid2-2*sd
    df["bb_pctB"]=(c-lo)/(up-lo); df["bb_width_pips"]=(up-lo)/PIP
    df["bb_squeeze"]=df["bb_width_pips"]/df["bb_width_pips"].rolling(50).mean()
    df["realized_vol_20"]=c.pct_change().rolling(20).std()*1e4
    df["range_pips"]=(h-l)/PIP; df["body_pips"]=(c-o)/PIP
    df["range_z20"]=(df["range_pips"]-df["range_pips"].rolling(20).mean())/df["range_pips"].rolling(20).std()
    rng=(h-l).replace(0,np.nan)
    df["body_to_range"]=(c-o)/rng
    df["upper_wick_ratio"]=(h-np.maximum(o,c))/rng
    df["lower_wick_ratio"]=(np.minimum(o,c)-l)/rng
    df["vol_z20"]=(v-v.rolling(20).mean())/v.rolling(20).std(ddof=0)
    df["vol_of_vol_20"]=df["atr14_pips"].rolling(20).std()
    bull=(c>o).astype(int); bear=(c<o).astype(int)
    df["consec_up"]=streak(bull)*bull; df["consec_dn"]=streak(bear)*bear
    df["velocity_3"]=c-c.shift(3); df["accel"]=df["velocity_3"].diff()
    df["dist_ema20_atr"]=(c-df["ema20"])/(df["atr14_pips"]*PIP).replace(0,np.nan)
    df["dist_ema50_atr"]=(c-df["ema50"])/(df["atr14_pips"]*PIP).replace(0,np.nan)
    hh14=h.rolling(14).max(); ll14=l.rolling(14).min()
    df["williams_r14"]=-100*(hh14-c)/(hh14-ll14).replace(0,np.nan)
    df["adx14"],df["plus_di"],df["minus_di"]=adx(h,l,c,14)
    for N in [5,20,50]:
        df[f"dist_to_{N}bar_high_pips"]=(h.rolling(N).max()-c)/PIP
        df[f"dist_to_{N}bar_low_pips"] =(c-l.rolling(N).min())/PIP
    df["date"]=df.index.normalize()
    df["dist_to_today_high_pips"]=(df.groupby("date")["high"].cummax()-c)/PIP
    df["dist_to_today_low_pips"] =(c-df.groupby("date")["low"].cummin())/PIP
    df=df.drop(columns=["date"])
    # UTC time features (broker M5 already converted to UTC above)
    df["hour_utc"]=df.index.hour
    df["dow"]=df.index.dayofweek
    return df


def add_h1_features(m5_df):
    """Derive H1 features by resampling broker M5 (already UTC) to H1."""
    h1 = m5_df[["open","high","low","close"]].resample("1h").agg(
        {"open":"first","high":"max","low":"min","close":"last"}).dropna()
    o=h1["open"]; h=h1["high"]; l=h1["low"]; c=h1["close"]
    h1["h1_rsi14"]=rsi(c,14)
    h1["h1_ema50"]=ema(c,50); h1["h1_ema200"]=ema(c,200)
    h1["h1_atr14_pips"]=atr(h,l,c,14)/PIP
    h1["h1_ema50_slope_pips"] =(h1["h1_ema50"] -h1["h1_ema50"].shift(24))/PIP
    h1["h1_ema200_slope_pips"]=(h1["h1_ema200"]-h1["h1_ema200"].shift(24))/PIP
    h1["h1_dist_ema50_pips"] =(c-h1["h1_ema50"])/PIP
    h1["h1_dist_ema200_pips"]=(c-h1["h1_ema200"])/PIP
    h1["h1_above_ema50"] =(c>h1["h1_ema50"]).astype(int)
    h1["h1_above_ema200"]=(c>h1["h1_ema200"]).astype(int)
    mid2=c.rolling(20).mean(); sd=c.rolling(20).std(ddof=0)
    h1["h1_bb_pctB"]=(c-(mid2-2*sd))/((mid2+2*sd)-(mid2-2*sd))
    u50=h1["h1_ema50_slope_pips"]>0; u200=h1["h1_ema200_slope_pips"]>0
    h1["h1_trend_dir"]=np.where(u50&u200,1,np.where(~u50&~u200,-1,0))
    h1["h1_dist_24h_high_pips"]=(h.rolling(24).max()-c)/PIP
    h1["h1_dist_24h_low_pips"] =(c-l.rolling(24).min())/PIP
    h1_keep=["h1_rsi14","h1_atr14_pips","h1_ema50_slope_pips","h1_ema200_slope_pips",
             "h1_dist_ema50_pips","h1_dist_ema200_pips","h1_above_ema50","h1_above_ema200",
             "h1_bb_pctB","h1_trend_dir","h1_dist_24h_high_pips","h1_dist_24h_low_pips"]
    h1_f=h1[h1_keep].dropna(subset=["h1_ema50_slope_pips"])
    merged=pd.merge_asof(
        m5_df.reset_index().sort_values("datetime"),
        h1_f.reset_index().rename(columns={"index":"h1_time"}).sort_values("h1_time"),
        left_on="datetime", right_on="h1_time", direction="backward")
    return merged.set_index("datetime").drop(columns=["h1_time"],errors="ignore")


def build_full_panel(ticks, m5):
    print(f"\n{'='*60}")
    print("STEP C: Build full panel (OHLC indicators + H1 features)")
    print(f"{'='*60}")
    df = compute_tick_features(ticks, m5)
    df = add_ohlc_indicators(df)
    df = add_h1_features(df)
    df.index.name = "datetime"
    df = df.sort_index()
    print(f"  Panel shape: {df.shape}")
    df.to_csv(PANEL_OUT, compression="gzip", float_format="%.5f")
    print(f"  Saved → {PANEL_OUT}")
    return df


# ══════════════════════════════════════════════════════════════════════════════
# STEP D — Rebuild Stage 1 OR-ensemble + candidate datasets
# Matches script 56 logic exactly
# ══════════════════════════════════════════════════════════════════════════════
def build_or_ensemble(panel, dev_panel, dev_piv_times, scan_ctx, K, zone_pct):
    top = scan_ctx[scan_ctx["keep"]].sort_values("auc", ascending=False).head(K)
    union = np.zeros(len(panel), dtype=bool)
    for _, r in top.iterrows():
        feat = r["indicator"]
        if feat not in panel.columns: continue
        vals = dev_panel.loc[dev_piv_times[dev_piv_times.isin(dev_panel.index)], feat].dropna().values
        if len(vals) < 10: continue
        d = r["cohens_d"]
        if d >= 0:
            thresh = np.percentile(vals, 100 - zone_pct)
            mask = panel[feat].fillna(panel[feat].median()).values >= thresh
        else:
            thresh = np.percentile(vals, zone_pct)
            mask = panel[feat].fillna(panel[feat].median()).values <= thresh
        union |= mask
    return pd.Series(union, index=panel.index)


def build_candidates(panel, pivots, ctx, K, zone_pct, dev_panel, scan):
    sub_scan = scan[(scan["dimension"]=="trade_context") & (scan["class"]==ctx) & scan["keep"]]
    if sub_scan.empty: return None
    dev_piv = pivots[(pivots["trade_context"]==ctx) & (pivots.index >= DEV_START) & (pivots.index <= DEV_END)]
    if len(dev_piv) < 30: return None
    ens_mask = build_or_ensemble(panel, dev_panel, dev_piv.index, sub_scan, K, zone_pct)
    cands = panel[ens_mask].copy()
    cands["candidate_time"] = cands.index
    cands["target_class"] = ctx
    cands["y_in_class"] = False
    cands["y_tradeable"] = False
    for dt in dev_piv.index:
        for off in [-1, 0, 1]:
            bar = dt + pd.Timedelta(minutes=5*off)
            if bar in cands.index:
                cands.loc[bar, "y_in_class"] = True
                if pivots.loc[dt, "tradeable"]:
                    cands.loc[bar, "y_tradeable"] = True
    return cands


def rebuild_candidates_and_stage1(panel, pivots_dev, pivots_oos, scan):
    print(f"\n{'='*60}")
    print("STEP D: Rebuild Stage 1 thresholds + candidate datasets")
    print(f"{'='*60}")
    dev_panel = panel[DEV_START:DEV_END]
    stage1 = {}
    for ctx, (zone_pct, K) in OP_POINTS.items():
        sub = scan[(scan["dimension"]=="trade_context") & (scan["class"]==ctx) & scan["keep"]]
        piv = pivots_dev[pivots_dev["trade_context"]==ctx]
        rules = []
        for _, r in sub.sort_values("auc", ascending=False).head(K).iterrows():
            feat = r["indicator"]
            if feat not in dev_panel.columns: continue
            piv_times = piv.index[piv.index.isin(dev_panel.index)]
            vals = dev_panel.loc[piv_times, feat].dropna().values
            if len(vals) < 10: continue
            d = r["cohens_d"]
            direction = ">=" if d >= 0 else "<="
            thresh = float(np.percentile(vals, 100-zone_pct if d>=0 else zone_pct))
            rules.append({"indicator": feat, "direction": direction,
                          "threshold": round(thresh, 6),
                          "cohens_d": round(float(d), 3), "auc": round(float(r["auc"]), 3)})
        stage1[ctx] = {"zone_pct": zone_pct, "K": K, "rules": rules}
        print(f"  {ctx}: {len(rules)} rules")

    with open(STAGE1_OUT, "w") as f: json.dump(stage1, f, indent=2)
    print(f"  Stage 1 thresholds → {STAGE1_OUT}")

    for split, piv, tag in [("DEV", pivots_dev, "DEV"), ("OOS", pivots_oos, "OOS")]:
        sub_panel = panel[DEV_START:DEV_END] if split=="DEV" else panel[OOS_START:OOS_END]
        for ctx, (zone_pct, K) in OP_POINTS.items():
            sub_scan = scan[(scan["dimension"]=="trade_context") & (scan["class"]==ctx) & scan["keep"]]
            if sub_scan.empty: continue
            piv_ctx = piv[piv["trade_context"]==ctx]
            # For OOS: use DEV pivot times to compute thresholds (same logic as Stage 1)
            dev_piv_for_threshold = pivots_dev[pivots_dev["trade_context"]==ctx]
            ens_mask = build_or_ensemble(sub_panel, dev_panel, dev_piv_for_threshold.index, sub_scan, K, zone_pct)
            cands = sub_panel[ens_mask].copy()
            cands["candidate_time"] = cands.index
            cands["target_class"] = ctx
            cands["y_tradeable"] = False
            for dt in piv_ctx.index[piv_ctx.index.isin(cands.index)]:
                for off in [-1, 0, 1]:
                    bar = dt + pd.Timedelta(minutes=5*off)
                    if bar in cands.index and piv.loc[dt, "tradeable"]:
                        cands.loc[bar, "y_tradeable"] = True
            out_f = f"{CAND_DIR}/candidates_{tag}_{ctx}.csv"
            cands.to_csv(out_f, index=False)
            print(f"  {tag} {ctx}: {len(cands):,} candidates, {cands['y_tradeable'].sum()} positives")
    return stage1


# ══════════════════════════════════════════════════════════════════════════════
# STEP E — Retrain GBMs on broker-data candidates (matches script 82)
# ══════════════════════════════════════════════════════════════════════════════
def retrain_gbms():
    print(f"\n{'='*60}")
    print("STEP E: Retrain GBMs on broker-data candidates")
    print(f"{'='*60}")
    os.makedirs(MODEL_DIR, exist_ok=True)
    all_feats = {}
    aucs = {}
    for ctx in CLASSES:
        dev_f = f"{CAND_DIR}/candidates_DEV_{ctx}.csv"
        oos_f = f"{CAND_DIR}/candidates_OOS_{ctx}.csv"
        if not os.path.exists(dev_f): print(f"  skip {ctx}: missing dev candidates"); continue
        dev = pd.read_csv(dev_f, parse_dates=["candidate_time"])
        feats = [c for c in dev.columns if c not in NON_FEAT
                 and pd.api.types.is_numeric_dtype(dev[c])
                 and dev[c].isna().mean() < 0.1]
        all_feats[ctx] = feats
        X = dev[feats].fillna(dev[feats].median()).values
        y = dev["y_tradeable"].astype(int).values
        spw = (len(y) - y.sum()) / max(y.sum(), 1)
        sw = np.where(y==1, spw, 1.0)
        gbm = HistGradientBoostingClassifier(
            max_iter=400, learning_rate=0.05, max_depth=6, max_leaf_nodes=31,
            min_samples_leaf=30, l2_regularization=0.2,
            early_stopping=True, validation_fraction=0.15, n_iter_no_change=30,
            random_state=42)
        gbm.fit(X, y, sample_weight=sw)
        probs = gbm.predict_proba(X)[:,1]
        auc = roc_auc_score(y, probs) if y.sum() > 0 else 0
        aucs[ctx] = auc
        medians = {c: float(dev[c].median()) for c in feats}
        pkl = {"model": gbm, "features": feats, "feature_medians": medians}
        path = f"{MODEL_DIR}/gbm_{ctx}.pkl"
        with open(path, "wb") as f: pickle.dump(pkl, f)

        oos_auc = "?"
        if os.path.exists(oos_f):
            oos = pd.read_csv(oos_f, parse_dates=["candidate_time"])
            common = [c for c in feats if c in oos.columns]
            if common and "y_tradeable" in oos.columns:
                Xo = oos[feats].fillna(dev[feats].median()).values
                yo = oos["y_tradeable"].astype(int).values
                if yo.sum() > 0:
                    oos_auc = f"{roc_auc_score(yo, gbm.predict_proba(Xo)[:,1]):.3f}"
        print(f"  {ctx}: in-AUC={auc:.3f}  oos-AUC={oos_auc}  features={len(feats)}")

    # Update manifest
    with open(f"{MODEL_DIR}/manifest.json") as f: manifest = json.load(f)
    manifest["feature_lists"] = all_feats
    manifest["broker_retrained"] = True
    manifest["retrained_on"] = "broker_ticks_RoboForex"
    with open(f"{MODEL_DIR}/manifest.json", "w") as f: json.dump(manifest, f, indent=2)
    print(f"\n  Models saved to {MODEL_DIR}")
    print(f"  Manifest updated")
    return aucs


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════
def main():
    print("VECTOR003 Broker Data Rebuild Pipeline")
    print("="*60)

    # Check if calibrated panel already exists (from step 84)
    if os.path.exists(CALIBRATED_PANEL):
        print(f"\nUsing pre-calibrated panel: {CALIBRATED_PANEL}")
        panel = pd.read_csv(CALIBRATED_PANEL, parse_dates=["datetime"])
        panel = panel.set_index("datetime").sort_index()
        print(f"  Shape: {panel.shape}")
    else:
        # A: Load ticks + resample to M5
        ticks = load_broker_ticks()
        m5 = ticks_to_m5_ohlc(ticks)
        # C: Build full panel (B is embedded in build_full_panel)
        panel = build_full_panel(ticks, m5)

    # Load pivot maps (existing Dukascopy ZZ pivots, same prices just shifted time)
    print("\nLoading pivot maps...")
    piv_dev = pd.read_csv(PIVOT_MAP_DEV, parse_dates=["pivot_time"]).set_index("pivot_time")
    piv_oos = pd.read_csv(PIVOT_MAP_OOS, parse_dates=["pivot_time"]).set_index("pivot_time") if os.path.exists(PIVOT_MAP_OOS) else pd.DataFrame()

    # The pivot times in the map are UTC (Dukascopy). Our panel is now also UTC. Match directly.
    print(f"  DEV pivots: {len(piv_dev):,}  OOS pivots: {len(piv_oos):,}")

    # Load indicator scan (same features, class-specific AUC scores)
    scan = pd.read_csv(SCAN_CSV)

    # D: Rebuild Stage 1 thresholds + candidate datasets
    stage1 = rebuild_candidates_and_stage1(panel, piv_dev, piv_oos, scan)

    # E: Retrain GBMs
    aucs = retrain_gbms()

    print(f"\n{'='*60}")
    print("DONE — broker-retrained models ready.")
    print("Next: restart bridge, recompile EA, run Strategy Tester.")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
