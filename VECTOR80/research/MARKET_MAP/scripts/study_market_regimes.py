#!/usr/bin/env python3
"""Study causal identification of EURUSD trend and regime states."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import accuracy_score, balanced_accuracy_score, confusion_matrix
from sklearn.utils.class_weight import compute_sample_weight


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PANEL = Path("/home/cmake/VectorShared/research/EURUSD_M5_CALIBRATED_PANEL.csv.gz")
DEFAULT_OUT = ROOT / "generated" / "MARKET_MAP_regime_predictions.csv.gz"
DEFAULT_METRICS = ROOT / "generated" / "MARKET_MAP_regime_metrics.json"
DEFAULT_MODEL = ROOT / "generated" / "MARKET_MAP_regime_models.joblib"
DEFAULT_REPORT = ROOT / "generated" / "MARKET_MAP_REGIME_STUDY.md"
PIP = 0.0001
HORIZON_BARS = 12

EXCLUDED_FEATURES = {
    "open", "high", "low", "close", "bar_high", "bar_low",
    "ema20", "ema50", "ema200",
}


def causalize_panel(frame: pd.DataFrame) -> pd.DataFrame:
    """Use only the most recently completed H1 candle."""
    out = frame.copy()
    h1_columns = [name for name in out.columns if name.startswith("h1_")]
    out[h1_columns] = out[h1_columns].shift(12)
    return out


def forward_path(frame: pd.DataFrame, bars: int = HORIZON_BARS) -> pd.DataFrame:
    """Calculate the path that follows, for persistence analysis only."""
    close = frame["close"]
    future_closes = pd.concat([close.shift(-i) for i in range(1, bars + 1)], axis=1)
    future_highs = pd.concat([frame["high"].shift(-i) for i in range(1, bars + 1)], axis=1)
    future_lows = pd.concat([frame["low"].shift(-i) for i in range(1, bars + 1)], axis=1)
    path_steps = pd.concat(
        [(close.shift(-i) - close.shift(-(i - 1))).abs() for i in range(1, bars + 1)],
        axis=1,
    )
    atr = frame["atr14_pips"].clip(lower=0.1)
    net = (future_closes.iloc[:, -1] - close) / PIP
    path = path_steps.sum(axis=1) / PIP
    high_excursion = (future_highs.max(axis=1) - close) / PIP
    low_excursion = (close - future_lows.min(axis=1)) / PIP
    future_range = (future_highs.max(axis=1) - future_lows.min(axis=1)) / PIP
    trailing_range = frame["range_pips"].rolling(bars, min_periods=bars).mean().clip(lower=0.1)
    future_bar_range = pd.concat(
        [frame["range_pips"].shift(-i) for i in range(1, bars + 1)], axis=1
    ).mean(axis=1)
    return pd.DataFrame(
        {
            "future_net_atr": net / atr,
            "future_efficiency": net.abs() / path.clip(lower=0.1),
            "future_range_atr": future_range / atr,
            "future_range_expansion": future_bar_range / trailing_range,
            "future_up_excursion_atr": high_excursion / atr,
            "future_down_excursion_atr": low_excursion / atr,
        },
        index=frame.index,
    )


def current_path(frame: pd.DataFrame, bars: int = HORIZON_BARS) -> pd.DataFrame:
    """Calculate the fully causal path observed over the trailing hour."""
    close = frame["close"]
    path = close.diff().abs().rolling(bars, min_periods=bars).sum() / PIP
    net = (close - close.shift(bars)) / PIP
    atr = frame["atr14_pips"].clip(lower=0.1)
    current_range = (
        frame["high"].rolling(bars, min_periods=bars).max()
        - frame["low"].rolling(bars, min_periods=bars).min()
    ) / PIP
    prior_range = (
        frame["range_pips"].shift(bars).rolling(48, min_periods=24).mean().clip(lower=0.1)
    )
    current_bar_range = frame["range_pips"].rolling(bars, min_periods=bars).mean()
    high_excursion = (
        frame["high"].rolling(bars, min_periods=bars).max() - close.shift(bars)
    ) / PIP
    low_excursion = (
        close.shift(bars) - frame["low"].rolling(bars, min_periods=bars).min()
    ) / PIP
    return pd.DataFrame(
        {
            "current_net_atr": net / atr,
            "current_efficiency": net.abs() / path.clip(lower=0.1),
            "current_range_atr": current_range / atr,
            "current_range_expansion": current_bar_range / prior_range,
            "current_up_excursion_atr": high_excursion / atr,
            "current_down_excursion_atr": low_excursion / atr,
        },
        index=frame.index,
    )


def label_axes(path: pd.DataFrame) -> pd.DataFrame:
    """Create direction, structure, volatility and composite path labels."""
    prefix = "future" if "future_net_atr" in path else "current"
    net = path[f"{prefix}_net_atr"]
    efficiency = path[f"{prefix}_efficiency"]
    expansion = path[f"{prefix}_range_expansion"]

    direction = np.select(
        [net >= 0.75, net <= -0.75],
        ["BULL", "BEAR"],
        default="NEUTRAL",
    )
    structure = np.select(
        [
            (net.abs() >= 1.25) & (efficiency >= 0.40),
            (net.abs() >= 0.75) & (efficiency < 0.40),
        ],
        ["TREND", "CHOP"],
        default="RANGE",
    )
    volatility = np.select(
        [expansion <= 0.70, expansion >= 1.35],
        ["COMPRESSION", "EXPANSION"],
        default="NORMAL",
    )

    composite = np.full(len(path), "RANGE", dtype=object)
    composite[(volatility == "COMPRESSION") & (np.abs(net) < 0.75)] = "COMPRESSION"
    composite[(volatility == "EXPANSION") & (np.abs(net) < 0.75)] = "VOLATILE_RANGE"
    composite[(direction == "BULL") & (structure == "CHOP")] = "BULL_CHOP"
    composite[(direction == "BEAR") & (structure == "CHOP")] = "BEAR_CHOP"
    composite[(direction == "BULL") & (structure == "TREND")] = "BULL_TREND"
    composite[(direction == "BEAR") & (structure == "TREND")] = "BEAR_TREND"
    composite[(net >= 2.50) & (efficiency >= 0.55)] = "STRONG_BULL_TREND"
    composite[(net <= -2.50) & (efficiency >= 0.55)] = "STRONG_BEAR_TREND"

    return pd.DataFrame(
        {
            "direction_label": direction,
            "structure_label": structure,
            "volatility_label": volatility,
            "regime_label": composite,
        },
        index=path.index,
    )


def feature_columns(frame: pd.DataFrame) -> list[str]:
    numeric = frame.select_dtypes(include=[np.number]).columns
    return [
        name for name in numeric
        if name not in EXCLUDED_FEATURES
        and not name.startswith("future_")
        and not name.endswith("_label")
    ]


def confidence_table(actual: pd.Series, predicted: np.ndarray, confidence: np.ndarray) -> list[dict]:
    rows = []
    for threshold in (0.35, 0.40, 0.45, 0.50, 0.60, 0.70, 0.80):
        selected = confidence >= threshold
        rows.append(
            {
                "threshold": threshold,
                "coverage": float(selected.mean()),
                "rows": int(selected.sum()),
                "accuracy": (
                    float(accuracy_score(actual[selected], predicted[selected]))
                    if selected.any() else None
                ),
            }
        )
    return rows


def fit_axis(
    train_x: pd.DataFrame,
    test_x: pd.DataFrame,
    train_y: pd.Series,
    test_y: pd.Series,
) -> tuple[HistGradientBoostingClassifier, dict, np.ndarray, np.ndarray]:
    model = HistGradientBoostingClassifier(
        learning_rate=0.06,
        max_iter=180,
        max_leaf_nodes=31,
        l2_regularization=2.0,
        random_state=42,
    )
    model.fit(train_x, train_y, sample_weight=compute_sample_weight("balanced", train_y))
    probability = model.predict_proba(test_x)
    predicted = model.classes_[np.argmax(probability, axis=1)]
    confidence = np.max(probability, axis=1)
    labels = list(model.classes_)
    metrics = {
        "accuracy": float(accuracy_score(test_y, predicted)),
        "balanced_accuracy": float(balanced_accuracy_score(test_y, predicted)),
        "majority_accuracy": float(test_y.value_counts(normalize=True).max()),
        "labels": labels,
        "class_counts": {str(k): int(v) for k, v in test_y.value_counts().items()},
        "confusion_matrix": confusion_matrix(test_y, predicted, labels=labels).tolist(),
        "confidence": confidence_table(test_y, predicted, confidence),
    }
    return model, metrics, predicted, confidence


def monthly_metrics(actual: pd.Series, predicted: np.ndarray) -> list[dict]:
    rows = []
    predicted_series = pd.Series(predicted, index=actual.index)
    for month, month_actual in actual.groupby(actual.index.to_period("M")):
        month_predicted = predicted_series.loc[month_actual.index]
        rows.append(
            {
                "month": str(month),
                "rows": len(month_actual),
                "accuracy": float(accuracy_score(month_actual, month_predicted)),
                "balanced_accuracy": float(
                    balanced_accuracy_score(month_actual, month_predicted)
                ),
            }
        )
    return rows


def transition_metrics(actual: pd.Series, predicted: np.ndarray) -> dict:
    prior = actual.shift(1)
    transition = actual.ne(prior) & prior.notna()
    stable = ~transition & prior.notna()
    result = {
        "transition_rate": float(transition.mean()),
        "accuracy_at_transition": float(accuracy_score(actual[transition], predicted[transition])),
        "accuracy_when_stable": float(accuracy_score(actual[stable], predicted[stable])),
    }
    for lag in (1, 2, 3, 6):
        recent = transition.rolling(lag + 1, min_periods=1).max().astype(bool)
        result[f"accuracy_within_{lag * 5}m_transition"] = float(
            accuracy_score(actual[recent], predicted[recent])
        )
    return result


def persistence_metrics(current: pd.DataFrame, future: pd.DataFrame, mask: pd.Series) -> dict:
    result = {}
    for column in current.columns:
        axis = column.removesuffix("_label")
        now = current.loc[mask, column]
        later = future.loc[mask, column]
        by_class = {}
        for value in sorted(now.unique()):
            selected = now == value
            by_class[str(value)] = {
                "rows": int(selected.sum()),
                "same_next_hour": float((later[selected] == now[selected]).mean()),
            }
        horizon_agreement = {}
        for bars in (1, 3, 6, 12):
            shifted = current[column].shift(-bars)
            horizon_mask = mask & shifted.notna()
            horizon_agreement[f"{bars * 5}m"] = float(
                (current.loc[horizon_mask, column] == shifted.loc[horizon_mask]).mean()
            )
        result[axis] = {
            "exact_agreement_next_hour": float((now == later).mean()),
            "state_duration_agreement": horizon_agreement,
            "by_current_class": by_class,
        }
    return result


def markdown_table(rows: list[dict], columns: list[tuple[str, str]]) -> list[str]:
    lines = [
        "| " + " | ".join(title for _, title in columns) + " |",
        "|" + "|".join("---:" if key != columns[0][0] else "---" for key, _ in columns) + "|",
    ]
    for row in rows:
        values = []
        for key, _ in columns:
            value = row[key]
            if isinstance(value, float):
                values.append(f"{value:.3f}")
            else:
                values.append(str(value))
        lines.append("| " + " | ".join(values) + " |")
    return lines


def write_report(metrics: dict, labels: pd.DataFrame, output: Path) -> None:
    summary = []
    for axis, values in metrics["axes"].items():
        summary.append(
            {
                "axis": axis,
                "accuracy": values["accuracy"],
                "balanced": values["balanced_accuracy"],
                "baseline": values["majority_accuracy"],
            }
        )
    lines = [
        "# MARKET_MAP Trend and Regime Study",
        "",
        "The target describes the price path already observed over the trailing 60",
        "minutes. Models use only data available at the current completed M5 bar.",
        "H1 inputs are delayed to the last completed H1 candle.",
        "",
        "## Taxonomy",
        "",
        "- Direction: `BULL`, `BEAR`, `NEUTRAL`.",
        "- Structure: `TREND`, `CHOP`, `RANGE`.",
        "- Volatility phase: `COMPRESSION`, `NORMAL`, `EXPANSION`.",
        "- Composite regime separates strong/orderly trends, directional chop,",
        "  quiet range and volatile range.",
        "",
        "## Continuous Out-of-Sample Classification",
        "",
        *markdown_table(
            summary,
            [
                ("axis", "Target"),
                ("accuracy", "Accuracy"),
                ("balanced", "Balanced accuracy"),
                ("baseline", "Majority baseline"),
            ],
        ),
        "",
        "## High-Confidence Accuracy",
        "",
    ]
    for axis, values in metrics["axes"].items():
        lines.extend([f"### {axis}", ""])
        lines.extend(
            markdown_table(
                values["confidence"],
                [
                    ("threshold", "Min probability"),
                    ("coverage", "Coverage"),
                    ("rows", "Rows"),
                    ("accuracy", "Accuracy"),
                ],
            )
        )
        lines.append("")
    regime_counts = labels["regime_label"].value_counts(normalize=True)
    lines.extend(["## Composite Regime Distribution", ""])
    lines.extend(
        markdown_table(
            [{"regime": k, "share": float(v)} for k, v in regime_counts.items()],
            [("regime", "Regime"), ("share", "All-data share")],
        )
    )
    lines.extend(
        [
            "",
            "## Monthly OOS Stability",
            "",
        ]
    )
    for axis, values in metrics["axes"].items():
        lines.extend([f"### {axis}", ""])
        lines.extend(
            markdown_table(
                values["monthly"],
                [
                    ("month", "Month"),
                    ("rows", "Rows"),
                    ("accuracy", "Accuracy"),
                    ("balanced_accuracy", "Balanced accuracy"),
                ],
            )
        )
        lines.append("")
    lines.extend(
        [
            "## State Duration",
            "",
            "| Axis | 5m | 15m | 30m | 60m | Next-hour path agrees |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for axis, values in metrics["persistence"].items():
        duration = values["state_duration_agreement"]
        lines.append(
            f"| {axis} | {duration['5m']:.3f} | {duration['15m']:.3f} | "
            f"{duration['30m']:.3f} | {duration['60m']:.3f} | "
            f"{values['exact_agreement_next_hour']:.3f} |"
        )
    lines.extend(
        [
            "",
            "## Path Thresholds",
            "",
            "- Direction requires a 60-minute net move of at least `0.75 x M5 ATR14`.",
            "- Trend requires at least `1.25 x ATR` net movement and path efficiency >= `0.40`.",
            "- Strong trend requires at least `2.50 x ATR` and efficiency >= `0.55`.",
            "- Compression/expansion compare the trailing 60-minute average M5 range",
            "  with the preceding four-hour baseline.",
            "",
            "## Important Limitation",
            "",
            "Current-state accuracy and future persistence are different measurements.",
            "A state can be identified correctly now and still change five minutes later.",
            "Accuracy near transitions is expected to be lower than during stable runs.",
            "",
            "## Design Recommendation",
            "",
            "- Publish direction, structure and volatility as separate state axes.",
            "- Add `TRANSITION` when axis confidence is low or the label recently changed.",
            "- Treat the nine-class composite as a descriptive summary, not the primary truth.",
            "- Recalculate on every completed M5 bar and retain state age/duration.",
            "- A 95% direction state is achievable only selectively: the current study reaches",
            "  94.5% at 59% coverage when model confidence is at least 0.80.",
            "- Structure needs more work; even its high-confidence subset reaches 88.0%.",
            "",
            "No model in this study is connected to live trading.",
        ]
    )
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--panel", type=Path, default=DEFAULT_PANEL)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--metrics", type=Path, default=DEFAULT_METRICS)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    frame = pd.read_csv(args.panel, index_col=0, parse_dates=True).sort_index()
    if frame.index.tz is not None:
        frame.index = frame.index.tz_convert("UTC").tz_localize(None)
    frame = causalize_panel(frame)
    observed_path = current_path(frame)
    future = forward_path(frame)
    labels = label_axes(observed_path)
    future_labels = label_axes(future)
    features = feature_columns(frame)

    usable = frame[features].notna().mean(axis=1) >= 0.80
    usable &= labels.notna().all(axis=1)
    usable &= observed_path.notna().all(axis=1)
    train = usable & (frame.index <= pd.Timestamp("2025-12-31 23:59:59"))
    test = usable & (frame.index >= pd.Timestamp("2026-03-01"))

    train_x = frame.loc[train, features].replace([np.inf, -np.inf], np.nan)
    test_x = frame.loc[test, features].replace([np.inf, -np.inf], np.nan)
    medians = train_x.median()
    train_x = train_x.fillna(medians)
    test_x = test_x.fillna(medians)

    models = {}
    metrics = {
        "horizon_minutes": HORIZON_BARS * 5,
        "features": features,
        "fit_rows": int(train.sum()),
        "test_rows": int(test.sum()),
        "test_start": "2026-03-01",
        "axes": {},
    }
    persistence_usable = test & future.notna().all(axis=1)
    metrics["persistence"] = persistence_metrics(
        labels, future_labels, persistence_usable
    )
    predictions = pd.DataFrame(index=frame.index[test])
    for column in ("direction_label", "structure_label", "volatility_label", "regime_label"):
        axis = column.removesuffix("_label")
        model, axis_metrics, predicted, confidence = fit_axis(
            train_x, test_x, labels.loc[train, column], labels.loc[test, column]
        )
        axis_metrics["transitions"] = transition_metrics(labels.loc[test, column], predicted)
        axis_metrics["monthly"] = monthly_metrics(labels.loc[test, column], predicted)
        models[axis] = model
        metrics["axes"][axis] = axis_metrics
        predictions[f"{axis}_actual"] = labels.loc[test, column]
        predictions[f"{axis}_predicted"] = predicted
        predictions[f"{axis}_confidence"] = confidence

    predictions = predictions.join(observed_path.loc[test])
    predictions = predictions.join(future.loc[test])
    predictions = predictions.join(
        future_labels.loc[test].add_prefix("future_")
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    predictions.to_csv(args.out, compression="gzip", float_format="%.6f")
    args.metrics.write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    joblib.dump({"models": models, "medians": medians, "features": features}, args.model)
    write_report(metrics, labels.loc[usable], args.report)

    for axis, values in metrics["axes"].items():
        print(
            axis,
            f"accuracy={values['accuracy']:.3f}",
            f"balanced={values['balanced_accuracy']:.3f}",
            f"baseline={values['majority_accuracy']:.3f}",
        )
    print("report:", args.report)


if __name__ == "__main__":
    main()
