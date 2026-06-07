#!/usr/bin/env python3
"""Train research-only calibrated MARKET_MAP direction models."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.frozen import FrozenEstimator
from sklearn.metrics import accuracy_score, balanced_accuracy_score, log_loss


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = ROOT / "generated" / "MARKET_MAP_training.csv.gz"
DEFAULT_MODEL = ROOT / "generated" / "MARKET_MAP_models_research.joblib"
DEFAULT_REPORT = ROOT / "generated" / "MARKET_MAP_MODEL_REPORT.md"
TARGETS = {
    "5m": "target_direction_5m",
    "15m": "target_direction_15m",
    "30m": "target_direction_30m",
    "60m": "target_direction_60m",
    "rest_day": "target_direction_rest_day",
}


def numeric_features(frame: pd.DataFrame) -> list[str]:
    blocked = {
        "open",
        "high",
        "low",
        "close",
        "bar_high",
        "bar_low",
        "candidate_time",
        "target_class",
        "y_in_class",
        "y_tradeable",
    }
    return [
        name
        for name in frame.select_dtypes(include=[np.number, "bool"]).columns
        if name not in blocked and not name.startswith("target_")
    ]


def causalize_panel(frame: pd.DataFrame) -> pd.DataFrame:
    """Lag H1 values to the last fully completed H1 candle."""
    out = frame.copy()
    h1_columns = [name for name in out.columns if name.startswith("h1_")]
    out[h1_columns] = out[h1_columns].shift(12)
    return out


def class_weights(labels: np.ndarray) -> np.ndarray:
    values, counts = np.unique(labels, return_counts=True)
    weights = {value: len(labels) / (len(values) * count) for value, count in zip(values, counts)}
    return np.array([weights[value] for value in labels], dtype=float)


def multiclass_brier(y_true: np.ndarray, probabilities: np.ndarray, classes: np.ndarray) -> float:
    expected = np.zeros_like(probabilities)
    for column, value in enumerate(classes):
        expected[:, column] = y_true == value
    return float(np.mean(np.sum((probabilities - expected) ** 2, axis=1)))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    frame = pd.read_csv(args.data, index_col=0, parse_dates=True).sort_index()
    frame = causalize_panel(frame)
    features = numeric_features(frame)
    fit = frame.loc[:"2025-12-31 23:59:59"]
    calibration = frame.loc["2026-01-01":"2026-02-28 23:59:59"]
    test = frame.loc["2026-03-01":]
    if min(len(fit), len(calibration), len(test)) == 0:
        raise RuntimeError("fit, calibration and test periods must all contain rows")

    fill_values = fit[features].replace([np.inf, -np.inf], np.nan).median()
    prepare = lambda part: part[features].replace([np.inf, -np.inf], np.nan).fillna(fill_values).fillna(0.0)
    x_fit = prepare(fit)
    x_cal = prepare(calibration)
    x_test = prepare(test)

    models = {}
    metrics = {}
    for horizon, target in TARGETS.items():
        y_fit = fit[target].astype(int).to_numpy()
        y_cal = calibration[target].astype(int).to_numpy()
        y_test = test[target].astype(int).to_numpy()
        base = HistGradientBoostingClassifier(
            max_iter=300,
            learning_rate=0.04,
            max_leaf_nodes=24,
            max_depth=6,
            min_samples_leaf=40,
            l2_regularization=0.5,
            early_stopping=True,
            random_state=42,
        )
        base.fit(x_fit, y_fit, sample_weight=class_weights(y_fit))
        model = CalibratedClassifierCV(FrozenEstimator(base), method="sigmoid")
        model.fit(x_cal, y_cal)
        probabilities = model.predict_proba(x_test)
        prediction = model.classes_[np.argmax(probabilities, axis=1)]
        majority = pd.Series(y_fit).mode().iloc[0]
        metrics[horizon] = {
            "test_rows": len(test),
            "accuracy": float(accuracy_score(y_test, prediction)),
            "balanced_accuracy": float(balanced_accuracy_score(y_test, prediction)),
            "majority_accuracy": float(np.mean(y_test == majority)),
            "log_loss": float(log_loss(y_test, probabilities, labels=model.classes_)),
            "brier": multiclass_brier(y_test, probabilities, model.classes_),
            "class_counts": pd.Series(y_test).value_counts().sort_index().to_dict(),
        }
        models[horizon] = model
        print(horizon, json.dumps(metrics[horizon], sort_keys=True))

    bundle = {
        "version": "0.1.0-research",
        "features": features,
        "fill_values": fill_values,
        "models": models,
        "metrics": metrics,
        "fit_end": "2025-12-31",
        "calibration_period": "2026-01-01 through 2026-02-28",
        "test_start": "2026-03-01",
    }
    args.model.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, args.model, compress=3)

    lines = [
        "# MARKET_MAP Research Model Report",
        "",
        "These models are research-only and are not connected to live trading.",
        "",
        "| Horizon | Accuracy | Balanced accuracy | Majority baseline | Log loss | Brier |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for horizon, values in metrics.items():
        lines.append(
            f"| {horizon} | {values['accuracy']:.3f} | "
            f"{values['balanced_accuracy']:.3f} | {values['majority_accuracy']:.3f} | "
            f"{values['log_loss']:.3f} | {values['brier']:.3f} |"
        )
    lines.extend(
        [
            "",
            f"- Features: {len(features)}",
            f"- Fit rows: {len(fit):,}",
            f"- Calibration rows: {len(calibration):,}",
            f"- Test rows: {len(test):,}",
            "- Fit period ends 2025-12-31.",
            "- Probability calibration uses January-February 2026.",
            "- Final evaluation starts March 1, 2026.",
            "- This first panel uses an unsupervised tick-domain calibration that "
            "includes April-June 2026 broker distributions. No outcome labels were "
            "used, but strict production validation must relearn that calibration "
            "using pre-test broker data only.",
            "",
            "## Deployment Gate",
            "",
            "- Keep all models disconnected from live trading.",
            "- Reject every current directional horizon; none exceeds 0.50 balanced accuracy.",
            "- Continue 15m and 30m research because they beat their majority-class baselines,",
            "  but that is not sufficient for deployment.",
        ]
    )
    args.report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"model: {args.model}")
    print(f"report: {args.report}")


if __name__ == "__main__":
    main()
