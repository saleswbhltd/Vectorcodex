"""
Step 32 — Train on 2025 M5 (70K bars), test on 2026 M5.

The current 2026 sample has only ~100-160 positives per type for training.
The 2025 dataset has 2.3× more bars and proportionally more positives.
Tests whether class imbalance + small sample is the precision bottleneck.

Builds H1 features for both periods using the 17-month H1 dataset.
"""

import pandas as pd
import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score

M5_2025 = "/home/cmake/Vector/research/m5_deep.csv.gz"
M5_2026 = "/home/cmake/Vector/research/m5_2026_deep.csv.gz"
H1_SRC  = "/mnt/c/Users/cmake/Documents/MarketData/EURUSD/EURUSD_H1_20250101_20260601.csv"
PIP = 0.0001
ZZ_THRESH = 20

M5_FEATS = [
    "atr5","atr14_pips","atr50","atr_ratio_5_50","atr_pct100","vol_of_vol_20",
    "realized_vol_20","range_z20","bb_squeeze",
    "rsi14","stoch_k","stoch_d","williams_r14",
    "macd","macd_hist","bb_pctB","bb_width_pips",
    "body_pips","range_pips","body_to_range",
    "upper_wick_ratio","lower_wick_ratio",
    "consec_up","consec_dn",
    "dist_ema20_atr","dist_ema50_atr",
    "dist_to_5bar_high_pips","dist_to_5bar_low_pips",
    "dist_to_20bar_high_pips","dist_to_20bar_low_pips",
    "dist_to_today_high_pips","dist_to_today_low_pips",
    "velocity_3","accel","plus_di","minus_di","adx14","hour_utc",
]
H1_FEATS = [
    "h1_rsi14","h1_atr14_pips","h1_ema50_slope_pips","h1_ema200_slope_pips",
    "h1_dist_ema50_pips","h1_dist_ema200_pips","h1_above_ema50","h1_above_ema200",
    "h1_bb_pctB","h1_trend_dir","h1_dist_24h_high_pips","h1_dist_24h_low_pips",
]
FEATS = M5_FEATS + H1_FEATS

TYPE_MAP = {"BUY_SWING": "LL", "BUY_PULLBACK": "HL",
            "SELL_SWING": "HH", "SELL_PULLBACK": "LH"}


def detect_pivots(df, thresh_pips):
    thresh = thresh_pips * PIP
    h = df["high"].values; l = df["low"].values; t = df.index.values
    direction_up = h[1] >= h[0]
    ext = h[1] if direction_up else l[1]; ext_i = 1
    out = []
    prev_h = None; prev_l = None
    for i in range(2, len(df)):
        if direction_up:
            if h[i] > ext: ext, ext_i = h[i], i
            elif l[i] <= ext - thresh:
                lbl = "H0" if prev_h is None else ("HH" if ext > prev_h else "LH")
                out.append((t[ext_i], lbl)); prev_h = ext
                direction_up = False; ext, ext_i = l[i], i
        else:
            if l[i] < ext: ext, ext_i = l[i], i
            elif h[i] >= ext + thresh:
                lbl = "L0" if prev_l is None else ("HL" if ext > prev_l else "LL")
                out.append((t[ext_i], lbl)); prev_l = ext
                direction_up = True; ext, ext_i = h[i], i
    return out


def compute_h1(h1):
    o,h,l,c = h1["open"],h1["high"],h1["low"],h1["close"]
    def ema(s,n): return s.ewm(span=n,adjust=False).mean()
    def rsi(c,n=14):
        d = c.diff()
        g = d.clip(lower=0).ewm(alpha=1/n,adjust=False).mean()
        ls = (-d.clip(upper=0)).ewm(alpha=1/n,adjust=False).mean()
        return 100 - 100 / (1 + g/ls.replace(0,np.nan))
    def atr(h,l,c,n=14):
        tr = pd.concat([h-l,(h-c.shift()).abs(),(l-c.shift()).abs()],axis=1).max(axis=1)
        return tr.ewm(alpha=1/n,adjust=False).mean()
    h1["h1_rsi14"] = rsi(c,14)
    h1["h1_ema50"] = ema(c,50); h1["h1_ema200"] = ema(c,200)
    h1["h1_atr14_pips"] = atr(h,l,c,14)/PIP
    h1["h1_ema50_slope_pips"]  = (h1["h1_ema50"]  - h1["h1_ema50"].shift(24))/PIP
    h1["h1_ema200_slope_pips"] = (h1["h1_ema200"] - h1["h1_ema200"].shift(24))/PIP
    h1["h1_dist_ema50_pips"]  = (c - h1["h1_ema50"])/PIP
    h1["h1_dist_ema200_pips"] = (c - h1["h1_ema200"])/PIP
    h1["h1_above_ema50"]  = (c > h1["h1_ema50"]).astype(int)
    h1["h1_above_ema200"] = (c > h1["h1_ema200"]).astype(int)
    mid = c.rolling(20).mean(); sd = c.rolling(20).std(ddof=0)
    h1["h1_bb_pctB"] = (c - (mid - 2*sd)) / ((mid + 2*sd) - (mid - 2*sd))
    u50 = h1["h1_ema50_slope_pips"]>0; u200 = h1["h1_ema200_slope_pips"]>0
    h1["h1_trend_dir"] = np.where(u50&u200,1, np.where(~u50&~u200,-1,0))
    h1["h1_dist_24h_high_pips"] = (h.rolling(24).max()-c)/PIP
    h1["h1_dist_24h_low_pips"]  = (c-l.rolling(24).min())/PIP
    return h1[H1_FEATS]


def main():
    print("loading H1 long-range...")
    h1 = pd.read_csv(H1_SRC)
    h1["datetime"] = pd.to_datetime(h1["datetime"], utc=True).dt.tz_localize(None)
    h1 = h1.set_index("datetime").sort_index()
    h1 = h1[~h1.index.duplicated(keep="first")]
    h1_f = compute_h1(h1).dropna()
    print(f"  H1 features: {len(h1_f):,}")

    print("loading M5 2025...")
    m5_25 = pd.read_csv(M5_2025, index_col=0, parse_dates=True)
    print(f"  2025 M5: {len(m5_25):,}")
    # Subset M5 features only (don't have h1 yet)
    m5_25 = m5_25[[c for c in M5_FEATS + ["open","high","low","close"] if c in m5_25.columns]]

    print("loading M5 2026...")
    m5_26 = pd.read_csv(M5_2026, index_col=0, parse_dates=True)
    print(f"  2026 M5: {len(m5_26):,}")
    m5_26 = m5_26[[c for c in M5_FEATS + ["open","high","low","close"] if c in m5_26.columns]]

    # Merge each with H1
    def attach(m5_df):
        m = pd.merge_asof(
            m5_df.reset_index().sort_values("datetime"),
            h1_f.reset_index().sort_values("datetime"),
            on="datetime", direction="backward"
        ).set_index("datetime")
        return m.dropna(subset=["h1_rsi14"])

    m25 = attach(m5_25); m26 = attach(m5_26)
    print(f"  2025 with H1: {len(m25):,}, 2026 with H1: {len(m26):,}")

    # Detect pivots in each
    def label(df):
        piv = detect_pivots(df, ZZ_THRESH)
        return pd.DataFrame(piv, columns=["pivot_time", "label"])

    piv_25 = label(m25)
    piv_26 = label(m26)
    print(f"  2025 pivots: {len(piv_25)}  2026 pivots: {len(piv_26)}")

    # Build per-type target series for both periods
    def build_target(df, piv, lbl):
        times = piv[piv["label"] == lbl]["pivot_time"]
        return pd.Series(df.index.isin(times), index=df.index)

    print("\n" + "="*78)
    print("Per-type GBM: train 2025+early-2026, test late-2026")
    print("="*78)

    # Combine 2025 + 2026 H1 (Jan-Mar) for training; test on Apr-Jun 2026
    SPLIT = "2026-04-01"
    combined = pd.concat([m25, m26]).sort_index()
    train = combined[combined.index < SPLIT]
    test  = combined[combined.index >= SPLIT]
    print(f"train: {len(train):,}   test: {len(test):,}")

    # Recompute pivots on the FULL combined frame so label timing is consistent
    piv_all = label(combined)
    print(f"combined pivots: {piv_all['label'].value_counts().to_dict()}")

    X = combined[FEATS].fillna(combined[FEATS].median())
    Xtr, Xte = X[combined.index < SPLIT].values, X[combined.index >= SPLIT].values

    summary = []
    for ptype, lbl in TYPE_MAP.items():
        target = build_target(combined, piv_all, lbl)
        ytr = target[combined.index < SPLIT].astype(int).values
        yte = target[combined.index >= SPLIT].astype(int).values
        if ytr.sum() < 50 or yte.sum() < 5:
            print(f"\n— {ptype}: skip (train_pos={ytr.sum()}, test_pos={yte.sum()})")
            continue
        print(f"\n— {ptype} — train_pos={ytr.sum()} test_pos={yte.sum()}")

        spw = (len(ytr) - ytr.sum()) / max(ytr.sum(), 1)
        sw = np.where(ytr == 1, spw, 1.0)
        gbm = HistGradientBoostingClassifier(
            max_iter=500, learning_rate=0.04,
            max_depth=6, max_leaf_nodes=31, min_samples_leaf=30,
            l2_regularization=0.2,
            early_stopping=True, validation_fraction=0.15, n_iter_no_change=30,
            random_state=42
        )
        gbm.fit(Xtr, ytr, sample_weight=sw)
        probs = gbm.predict_proba(Xte)[:, 1]
        auc = roc_auc_score(yte, probs)
        print(f"  OOS AUC: {auc:.3f}")

        target_te = target[combined.index >= SPLIT]
        pivot_zone = target_te.rolling(window=3, center=True, min_periods=1).max() > 0
        print(f"  thresholds (tol=±1):")
        best_p = 0; best_th = 0; best_n = 0
        for th in [0.50, 0.70, 0.80, 0.85, 0.90, 0.92, 0.95, 0.97, 0.99]:
            mask = pd.Series(probs >= th, index=test.index)
            n_sig = int(mask.sum())
            if n_sig == 0: continue
            signal_zone = mask.rolling(window=3, center=True, min_periods=1).max() > 0
            matches = int((mask & pivot_zone).sum())
            covered = int((target_te & signal_zone).sum())
            prec = matches / n_sig
            rec = covered / int(target_te.sum())
            print(f"    thr={th:.2f}  n={n_sig:4d}  prec={100*prec:5.1f}%  rec={100*rec:5.1f}%")
            if n_sig >= 5 and prec > best_p:
                best_p, best_th, best_n = prec, th, n_sig

        summary.append({"ptype": ptype, "AUC": auc, "best_p": best_p,
                        "best_th": best_th, "best_n": best_n})

    print(f"\n{'='*78}\nSUMMARY — train on 2025+early-2026, test late-2026\n{'='*78}")
    print(f"{'type':16s} {'AUC':>5s} {'best_prec':>10s} {'@thr':>6s} {'n':>5s}")
    for s in summary:
        print(f"{s['ptype']:16s} {s['AUC']:.3f} {100*s['best_p']:>9.1f}% "
              f"{s['best_th']:>5.2f} {s['best_n']:>5d}")


if __name__ == "__main__":
    main()
