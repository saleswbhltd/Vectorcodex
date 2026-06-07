"""
Step 45 — Stage 2 candidate quality model.

Stage 1 detects most pivots but fires on too many M5 bars. This script asks:
after Stage 1 has raised candidate bars, can a per-class model filter those
candidates into a useful real-time pivot detector?

Train/dev:
  2025-02-01 to 2026-02-28

OOS:
  2026-03-01 to 2026-06-01

Labels:
  A candidate bar is positive for class C if it fires within [-2, -1, 0] bars
  of a historical ZZ pivot of class C.

Outputs:
  stage2_candidate_quality.csv
  STAGE2_CANDIDATE_QUALITY.md
"""

import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score

PANEL = "/home/cmake/Vector/research/EURUSD_M5_FULL_PANEL.csv.gz"
GREEDY = "/home/cmake/Vector/research/greedy_cover_summary.csv"
OUT = "/home/cmake/Vector/research/stage2_candidate_quality.csv"
OUT_MD = "/home/cmake/Vector/research/STAGE2_CANDIDATE_QUALITY.md"

DEV_START = "2025-02-01"
DEV_END = "2026-02-28 23:59:59"
OOS_START = "2026-03-01"
OOS_END = "2026-06-01"

CLASSES = ["HH", "HL", "LH", "LL"]
PIP = 0.0001
ZZ_THRESH_PIPS = 20
LABEL_OFFSETS = [-2, -1, 0]

DROP_COLS = {
    "open", "high", "low", "close", "volume", "tick_volume",
    "bid_volume", "ask_volume", "ema20", "ema50", "ema200",
    "bar_high", "bar_low",
}

THRESHOLDS = [0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90, 0.95]


def detect_zz(df: pd.DataFrame, thresh_pips: float) -> pd.DataFrame:
    thresh = thresh_pips * PIP
    h = df["high"].values
    l = df["low"].values
    t = df.index.values
    direction_up = h[1] >= h[0]
    ext = h[1] if direction_up else l[1]
    ext_i = 1
    prev_h = None
    prev_l = None
    out = []
    for i in range(2, len(df)):
        if direction_up:
            if h[i] > ext:
                ext, ext_i = h[i], i
            elif l[i] <= ext - thresh:
                label = "H0" if prev_h is None else ("HH" if ext > prev_h else "LH")
                out.append((t[ext_i], ext_i, ext, True, label, t[i]))
                prev_h = ext
                direction_up = False
                ext, ext_i = l[i], i
        else:
            if l[i] < ext:
                ext, ext_i = l[i], i
            elif h[i] >= ext + thresh:
                label = "L0" if prev_l is None else ("HL" if ext > prev_l else "LL")
                out.append((t[ext_i], ext_i, ext, False, label, t[i]))
                prev_l = ext
                direction_up = True
                ext, ext_i = h[i], i
    return pd.DataFrame(out, columns=["pivot_time", "pivot_idx", "price", "is_high", "label", "confirm_time"])


def rule_mask(panel: pd.DataFrame, rule: pd.Series) -> np.ndarray:
    vals = panel[rule["indicator"]].replace([np.inf, -np.inf], np.nan)
    vals = vals.fillna(vals.median()).values.astype(float)
    if rule["op"] == ">=":
        return vals >= rule["threshold"]
    return vals <= rule["threshold"]


def class_stage1_mask(panel: pd.DataFrame, rules: pd.DataFrame, cls: str) -> np.ndarray:
    out = np.zeros(len(panel), dtype=bool)
    for _, r in rules[rules["class"] == cls].iterrows():
        out |= rule_mask(panel, r)
    return out


def target_mask_for_class(n: int, pivot_indices: np.ndarray) -> np.ndarray:
    y = np.zeros(n, dtype=bool)
    for idx in pivot_indices:
        for off in LABEL_OFFSETS:
            j = idx + off
            if 0 <= j < n:
                y[j] = True
    return y


def numeric_features(panel: pd.DataFrame) -> list[str]:
    feats = []
    for c in panel.columns:
        if c in DROP_COLS:
            continue
        if pd.api.types.is_numeric_dtype(panel[c]) and panel[c].nunique(dropna=True) > 5:
            feats.append(c)
    return feats


def prep_X(panel: pd.DataFrame, feats: list[str]) -> pd.DataFrame:
    X = panel[feats].replace([np.inf, -np.inf], np.nan).copy()
    for c in X.columns:
        X[c] = X[c].fillna(X[c].median())
    return X


def main():
    print("loading panel and rules...")
    panel = pd.read_csv(PANEL, index_col=0, parse_dates=True)
    panel = panel.loc[DEV_START:OOS_END].copy()
    rules = pd.read_csv(GREEDY)
    print(f"  bars: {len(panel):,}  {panel.index[0]} -> {panel.index[-1]}")
    print(f"  stage1 rules: {len(rules)}")

    piv = detect_zz(panel, ZZ_THRESH_PIPS)
    piv = piv[piv["label"].isin(CLASSES)].copy()
    print(f"  pivots full split: {len(piv):,}")
    print(f"  by class: {piv['label'].value_counts().to_dict()}")

    feats = numeric_features(panel)
    X_all = prep_X(panel, feats)
    dev_mask = (panel.index >= pd.Timestamp(DEV_START)) & (panel.index <= pd.Timestamp(DEV_END))
    oos_mask = (panel.index >= pd.Timestamp(OOS_START)) & (panel.index <= pd.Timestamp(OOS_END))

    rows = []
    md = ["# Stage 2 Candidate Quality", ""]
    md.append("Stage 1 fires are filtered with per-class HistGradientBoosting models.")
    md.append("")

    for cls in CLASSES:
        stage1 = class_stage1_mask(panel, rules, cls)
        cls_piv_idx = piv[piv["label"] == cls]["pivot_idx"].values.astype(int)
        target = target_mask_for_class(len(panel), cls_piv_idx)

        train_idx = np.where(stage1 & dev_mask)[0]
        test_idx = np.where(stage1 & oos_mask)[0]
        if len(train_idx) == 0 or len(test_idx) == 0:
            continue
        ytr = target[train_idx].astype(int)
        yte = target[test_idx].astype(int)

        print(f"\n{cls}: train candidates={len(train_idx):,} pos={ytr.sum()} | "
              f"OOS candidates={len(test_idx):,} pos={yte.sum()}")

        if ytr.sum() < 20 or yte.sum() < 5:
            print("  skip: not enough positives")
            continue

        spw = (len(ytr) - ytr.sum()) / max(ytr.sum(), 1)
        weights = np.where(ytr == 1, spw, 1.0)
        model = HistGradientBoostingClassifier(
            max_iter=500,
            learning_rate=0.04,
            max_leaf_nodes=24,
            max_depth=6,
            min_samples_leaf=25,
            l2_regularization=0.1,
            early_stopping=True,
            validation_fraction=0.15,
            n_iter_no_change=40,
            random_state=42,
        )
        model.fit(X_all.iloc[train_idx], ytr, sample_weight=weights)
        prob = model.predict_proba(X_all.iloc[test_idx])[:, 1]
        auc = roc_auc_score(yte, prob) if len(np.unique(yte)) == 2 else np.nan
        print(f"  OOS AUC={auc:.3f}")

        md += [f"## {cls}", ""]
        md.append(f"OOS AUC: `{auc:.3f}`")
        md.append("")
        md += ["| threshold | signals | precision | recall |"]
        md += ["|---:|---:|---:|---:|"]

        for th in THRESHOLDS:
            sig = prob >= th
            n_sig = int(sig.sum())
            hits = int((sig & (yte == 1)).sum())
            n_pos = int(yte.sum())
            precision = hits / n_sig if n_sig else 0.0
            recall = hits / n_pos if n_pos else 0.0
            rows.append({
                "class": cls,
                "threshold": th,
                "auc": auc,
                "train_candidates": len(train_idx),
                "train_pos": int(ytr.sum()),
                "oos_candidates": len(test_idx),
                "oos_pos": n_pos,
                "signals": n_sig,
                "hits": hits,
                "precision": precision,
                "recall": recall,
            })
            md.append(f"| {th:.2f} | {n_sig} | {100*precision:.1f}% | {100*recall:.1f}% |")
            print(f"    th={th:.2f} n={n_sig:5d} prec={100*precision:5.1f}% rec={100*recall:5.1f}%")
        md.append("")

    out = pd.DataFrame(rows)
    out.to_csv(OUT, index=False, float_format="%.6f")
    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(md))
    print(f"\nsaved -> {OUT}")
    print(f"saved -> {OUT_MD}")

    if not out.empty:
        print("\nBest OOS precision per class with at least 10 signals:")
        for cls in CLASSES:
            sub = out[(out["class"] == cls) & (out["signals"] >= 10)]
            if sub.empty:
                print(f"  {cls}: no threshold with >=10 signals")
                continue
            r = sub.sort_values(["precision", "recall"], ascending=False).iloc[0]
            print(
                f"  {cls}: th={r['threshold']:.2f}, signals={int(r['signals'])}, "
                f"precision={100*r['precision']:.1f}%, recall={100*r['recall']:.1f}%"
            )


if __name__ == "__main__":
    main()

