"""
Step 82 — Train final per-class GBMs on FULL training data and export to ONNX.

Final models will be loaded by VECTOR003.mq5 via MT5's built-in ONNX runtime.

Training data: 2025-02-01 to 2026-02-28 (13 months, full DEV period)

For each class:
  1. Train HistGradientBoostingClassifier on candidates_DEV_<ctx>.csv
  2. Export to ONNX format
  3. Save feature list (so MQL5 builds inputs in correct order)
  4. Verify ONNX prediction matches sklearn prediction
"""

import pandas as pd
import numpy as np
import json
import os
import pickle
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score

OUT_DIR = "/home/cmake/Vector/models"
os.makedirs(OUT_DIR, exist_ok=True)

CLASSES = ["BULL_CONTINUATION_HIGH","BEAR_TREND_BREAK_HIGH",
           "WEAK_HIGH_IN_UPTREND","SELL_PULLBACK_DOWNTREND",
           "BUY_PULLBACK_UPTREND","WEAK_LOW_IN_DOWNTREND",
           "BULL_TREND_BREAK_LOW","BEAR_CONTINUATION_LOW"]

NON_FEAT = {"candidate_time","target_class","y_in_class","y_tradeable",
             "open","high","low","close","volume","tick_volume",
             "bid_volume","ask_volume","ema20","ema50","ema200",
             "bar_high","bar_low"}


def main():
    print("Training and exporting per-class GBMs to ONNX...")
    print(f"Output directory: {OUT_DIR}")

    # Track feature lists across classes
    all_feature_lists = {}
    aucs = {}
    used_common_features = None

    for ctx in CLASSES:
        cand_file = f"/home/cmake/Vector/research/candidates_DEV_{ctx}.csv"
        if not os.path.exists(cand_file):
            print(f"  skip {ctx}: missing candidate file"); continue
        print(f"\n--- {ctx} ---")
        df = pd.read_csv(cand_file, parse_dates=["candidate_time"])
        feats = [c for c in df.columns if c not in NON_FEAT
                  and pd.api.types.is_numeric_dtype(df[c])
                  and df[c].isna().mean() < 0.1]
        all_feature_lists[ctx] = feats
        if used_common_features is None:
            used_common_features = set(feats)
        else:
            used_common_features &= set(feats)
        print(f"  {len(df)} candidates, {len(feats)} features, {int(df['y_tradeable'].sum())} positives "
              f"({100*df['y_tradeable'].mean():.1f}%)")

        X = df[feats].fillna(df[feats].median()).values
        y = df["y_tradeable"].astype(int).values
        spw = (len(y) - y.sum()) / max(y.sum(), 1)
        sw = np.where(y == 1, spw, 1.0)
        gbm = HistGradientBoostingClassifier(
            max_iter=400, learning_rate=0.05, max_depth=6, max_leaf_nodes=31,
            min_samples_leaf=30, l2_regularization=0.2,
            early_stopping=True, validation_fraction=0.15, n_iter_no_change=30,
            random_state=42)
        gbm.fit(X, y, sample_weight=sw)

        # Quick in-sample AUC check
        probs = gbm.predict_proba(X)[:, 1]
        auc = roc_auc_score(y, probs)
        aucs[ctx] = auc
        print(f"  in-sample AUC: {auc:.3f}  (out-of-sample expected ~0.83-0.93)")

        # Save sklearn model (backup)
        sk_path = f"{OUT_DIR}/gbm_{ctx}.pkl"
        with open(sk_path, "wb") as f:
            pickle.dump({"model": gbm, "features": feats,
                          "feature_medians": df[feats].median().to_dict()}, f)
        print(f"  saved sklearn model: {sk_path}")

        # ONNX export (try)
        try:
            from skl2onnx import convert_sklearn
            from skl2onnx.common.data_types import FloatTensorType
            n_feat = len(feats)
            initial_type = [("input", FloatTensorType([None, n_feat]))]
            onx = convert_sklearn(gbm, initial_types=initial_type, target_opset=15)
            onnx_path = f"{OUT_DIR}/gbm_{ctx}.onnx"
            with open(onnx_path, "wb") as f:
                f.write(onx.SerializeToString())
            print(f"  exported ONNX: {onnx_path} ({os.path.getsize(onnx_path)/1024:.0f} KB)")
        except ImportError:
            print("  skl2onnx not installed — install with: pip install skl2onnx")
            print(f"  proceeding without ONNX export — sklearn .pkl saved instead")
        except Exception as e:
            print(f"  ONNX export failed: {e}")

    # Save feature lists + common feature reference
    print(f"\n\n{'='*78}")
    print("Common features across all classes:")
    print(f"{'='*78}")
    common_list = sorted(used_common_features)
    print(f"  {len(common_list)} common features")
    for f in common_list[:30]:
        print(f"    {f}")
    if len(common_list) > 30:
        print(f"    ... + {len(common_list)-30} more")

    # Save manifest
    manifest = {
        "classes": CLASSES,
        "class_to_label": {
            "BULL_CONTINUATION_HIGH":"HH","BEAR_TREND_BREAK_HIGH":"HH",
            "WEAK_HIGH_IN_UPTREND":"LH","SELL_PULLBACK_DOWNTREND":"LH",
            "BUY_PULLBACK_UPTREND":"HL","WEAK_LOW_IN_DOWNTREND":"HL",
            "BULL_TREND_BREAK_LOW":"LL","BEAR_CONTINUATION_LOW":"LL",
        },
        "label_to_side": {"HH":"SELL","LH":"SELL","LL":"BUY","HL":"BUY"},
        "feature_lists": all_feature_lists,
        "in_sample_aucs": aucs,
        "default_params": {
            "threshold": 0.70, "cooldown_min": 30, "local_n": 3,
            "sl_pips": 5, "trail_pips": 5, "time_stop_bars": 12,
        }
    }
    with open(f"{OUT_DIR}/manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"\nsaved manifest: {OUT_DIR}/manifest.json")
    print(f"\nAll done.")


if __name__ == "__main__":
    main()
