#!/usr/bin/env python3
"""Study whether strength, volatility and time predict trend continuation."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.metrics import accuracy_score, balanced_accuracy_score, roc_auc_score

try:
    from scripts.validate_tradability_historical_holdout import prepare_adjusted_frame
except ModuleNotFoundError:
    from validate_tradability_historical_holdout import prepare_adjusted_frame


ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = Path(
    "/home/cmake/VectorShared/research/dukascopy/EURUSD/2023_2024/broker_adjusted"
)
DEFAULT_REPORT = ROOT / "generated" / "MARKET_MAP_TREND_TERMINATION_2024Q4.md"
DEFAULT_METRICS = ROOT / "generated" / "MARKET_MAP_trend_termination_metrics.json"
DEFAULT_PREDICTIONS = (
    ROOT / "generated" / "MARKET_MAP_trend_termination_2024Q4.csv.gz"
)
PIP = 0.0001
HORIZONS = (3, 6, 12)


def first_hit_label(
    favorable: np.ndarray,
    adverse: np.ndarray,
    target: np.ndarray,
    stop: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    target_hit = favorable >= target[:, None]
    stop_hit = adverse >= stop[:, None]
    target_index = np.where(target_hit.any(1), target_hit.argmax(1), 999)
    stop_index = np.where(stop_hit.any(1), stop_hit.argmax(1), 999)
    decisive = (target_index < 999) | (stop_index < 999)
    continuation = target_index < stop_index
    return continuation, decisive


def add_path_targets(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    direction = out["current_direction_label"].map(
        {"BULL": 1.0, "BEAR": -1.0, "NEUTRAL": 0.0}
    ).to_numpy()
    entry = out["close"].to_numpy()
    atr = out["atr14_pips"].clip(lower=1.0).to_numpy()
    target = np.maximum(2.0, atr * 0.75)
    stop = np.maximum(2.0, atr * 0.50)
    for bars in HORIZONS:
        highs = np.column_stack(
            [out["high"].shift(-step) for step in range(1, bars + 1)]
        )
        lows = np.column_stack(
            [out["low"].shift(-step) for step in range(1, bars + 1)]
        )
        up_favorable = (highs - entry[:, None]) / PIP
        up_adverse = (entry[:, None] - lows) / PIP
        down_favorable = (entry[:, None] - lows) / PIP
        down_adverse = (highs - entry[:, None]) / PIP
        favorable = np.where(direction[:, None] > 0, up_favorable, down_favorable)
        adverse = np.where(direction[:, None] > 0, up_adverse, down_adverse)
        continuation, decisive = first_hit_label(favorable, adverse, target, stop)
        minutes = bars * 5
        out[f"continue_{minutes}m"] = continuation
        out[f"decisive_{minutes}m"] = decisive & np.isfinite(highs).all(axis=1)
    return out


def add_model_features(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    minute = out.index.hour * 60 + out.index.minute
    angle = 2 * np.pi * minute / 1440.0
    out["time_sin"] = np.sin(angle)
    out["time_cos"] = np.cos(angle)
    out["dow_sin"] = np.sin(2 * np.pi * out.index.dayofweek / 5.0)
    out["dow_cos"] = np.cos(2 * np.pi * out.index.dayofweek / 5.0)
    out["is_bull"] = out["current_direction_label"].eq("BULL").astype(int)
    out["signed_imbalance"] = np.where(
        out["is_bull"].eq(1), out["imbalance"], -out["imbalance"]
    )
    out["signed_body_to_range"] = np.where(
        out["is_bull"].eq(1), out["body_to_range"], -out["body_to_range"]
    )
    out["directional_exhaustion"] = np.where(
        out["is_bull"].eq(1),
        out["ticks_at_high_pct"] - out["ticks_at_low_pct"],
        out["ticks_at_low_pct"] - out["ticks_at_high_pct"],
    )
    out["velocity_change"] = (
        out["tick_velocity_second_half"] - out["tick_velocity_first_half"]
    )
    return out


FEATURES = [
    "current_net_atr",
    "current_efficiency",
    "current_range_atr",
    "current_range_expansion",
    "atr14_pips",
    "atr_ratio_5_50",
    "atr_pct100",
    "vol_of_vol_20",
    "adx14",
    "plus_di",
    "minus_di",
    "rsi14",
    "bb_pctB",
    "dist_ema20_atr",
    "dist_ema50_atr",
    "range_z20",
    "signed_body_to_range",
    "tick_count",
    "median_tick_interval_ms",
    "max_tick_interval_ms",
    "spread_avg",
    "signed_imbalance",
    "velocity_change",
    "vel_ratio_2nd_to_1st",
    "directional_exhaustion",
    "max_run_up_pips_intrabar",
    "max_run_dn_pips_intrabar",
    "time_sin",
    "time_cos",
    "dow_sin",
    "dow_cos",
    "is_bull",
]


def load_data(archive: Path) -> pd.DataFrame:
    frames = []
    for year in (2023, 2024):
        path = archive / f"EURUSD_M5_broker_adjusted_{year}.csv.gz"
        frames.append(prepare_adjusted_frame(path))
    frame = pd.concat(frames).sort_index()
    frame = frame[~frame.index.duplicated(keep="first")]
    frame = add_model_features(add_path_targets(frame))
    active = frame["current_direction_label"].isin(["BULL", "BEAR"])
    active &= frame["current_structure_label"].isin(["TREND", "CHOP"])
    active &= frame["current_net_atr"].abs().ge(0.75)
    frame = frame[active].copy()
    new_episode = frame["current_direction_label"].ne(
        frame["current_direction_label"].shift()
    )
    new_episode |= frame.index.to_series().diff().gt(pd.Timedelta("10min"))
    return frame[new_episode].copy()


def confidence_table(actual: np.ndarray, probability: np.ndarray) -> list[dict]:
    rows = []
    confidence = np.maximum(probability, 1.0 - probability)
    predicted = probability >= 0.5
    for threshold in (0.55, 0.60, 0.65, 0.70, 0.75, 0.80):
        selected = confidence >= threshold
        rows.append(
            {
                "confidence": threshold,
                "coverage": float(selected.mean()),
                "rows": int(selected.sum()),
                "accuracy": (
                    float(accuracy_score(actual[selected], predicted[selected]))
                    if selected.any()
                    else None
                ),
            }
        )
    return rows


def interaction_table(
    test: pd.DataFrame, target: str, probability: np.ndarray
) -> pd.DataFrame:
    work = test.copy()
    work["actual_continue"] = work[target].astype(int)
    work["predicted_continue"] = probability
    work["strength_band"] = pd.cut(
        work["current_net_atr"].abs(),
        [-np.inf, 1.25, 2.5, np.inf],
        labels=["MODERATE", "STRONG", "EXTREME"],
    )
    work["volatility_phase"] = work["current_volatility_label"]
    work["time_block"] = pd.cut(
        work.index.hour,
        [-1, 5, 9, 13, 17, 23],
        labels=["00-05", "06-09", "10-13", "14-17", "18-23"],
    )
    grouped = work.groupby(
        ["current_direction_label", "strength_band", "volatility_phase", "time_block"],
        observed=True,
    )
    return grouped.agg(
        rows=("actual_continue", "size"),
        continuation_rate=("actual_continue", "mean"),
        predicted_rate=("predicted_continue", "mean"),
        mean_efficiency=("current_efficiency", "mean"),
        mean_expansion=("current_range_expansion", "mean"),
        mean_exhaustion=("directional_exhaustion", "mean"),
    ).reset_index()


def monday_morning_table(test: pd.DataFrame, probability: np.ndarray, target: str) -> pd.DataFrame:
    work = test[
        (test.index.dayofweek == 0)
        & (test.index.hour >= 6)
        & (test.index.hour < 10)
    ].copy()
    work["actual_continue"] = work[target].astype(int)
    work["predicted_continue"] = probability[test.index.get_indexer(work.index)]
    work["strength_band"] = pd.cut(
        work["current_net_atr"].abs(),
        [-np.inf, 1.25, 2.5, np.inf],
        labels=["MODERATE", "STRONG", "EXTREME"],
    )
    grouped = work.groupby(
        ["current_direction_label", "strength_band", "current_volatility_label"],
        observed=True,
    )
    return grouped.agg(
        rows=("actual_continue", "size"),
        continuation_rate=("actual_continue", "mean"),
        predicted_rate=("predicted_continue", "mean"),
        efficiency=("current_efficiency", "mean"),
        range_expansion=("current_range_expansion", "mean"),
    ).reset_index()


def wilson_interval(successes: int, rows: int, z: float = 1.96) -> tuple[float, float]:
    rate = successes / rows
    denominator = 1.0 + z * z / rows
    center = (rate + z * z / (2.0 * rows)) / denominator
    margin = (
        z
        * math.sqrt(rate * (1.0 - rate) / rows + z * z / (4.0 * rows * rows))
        / denominator
    )
    return center - margin, center + margin


def aggregate_monday(monday: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (horizon, direction, volatility), group in monday.groupby(
        ["horizon_min", "current_direction_label", "current_volatility_label"]
    ):
        total = int(group["rows"].sum())
        successes = int(round((group["rows"] * group["continuation_rate"]).sum()))
        lower, upper = wilson_interval(successes, total)
        rows.append(
            {
                "horizon_min": horizon,
                "direction": direction,
                "volatility": volatility,
                "episodes": total,
                "continuation_rate": successes / total,
                "ci95_low": lower,
                "ci95_high": upper,
            }
        )
    return pd.DataFrame(rows)


def markdown(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "No rows."
    display = frame.copy()
    for column in display.select_dtypes(include=[np.number]):
        display[column] = display[column].round(3)
    columns = list(display.columns)
    lines = [
        "| " + " | ".join(columns) + " |",
        "|" + "|".join("---" for _ in columns) + "|",
    ]
    for row in display.itertuples(index=False, name=None):
        lines.append("| " + " | ".join(str(value) for value in row) + " |")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, default=ARCHIVE)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--metrics", type=Path, default=DEFAULT_METRICS)
    parser.add_argument("--predictions", type=Path, default=DEFAULT_PREDICTIONS)
    args = parser.parse_args()

    frame = load_data(args.archive)
    train_mask = frame.index < pd.Timestamp("2024-10-01")
    test_mask = (
        (frame.index >= pd.Timestamp("2024-10-01"))
        & (frame.index < pd.Timestamp("2025-01-01"))
    )
    results = {}
    prediction_output = pd.DataFrame(index=frame.index[test_mask])
    importance_rows = []
    interaction_outputs = []
    monday_outputs = []

    for bars in HORIZONS:
        minutes = bars * 5
        target = f"continue_{minutes}m"
        decisive = f"decisive_{minutes}m"
        train = frame[train_mask & frame[decisive]].copy()
        test = frame[test_mask & frame[decisive]].copy()
        train_x = train[FEATURES].replace([np.inf, -np.inf], np.nan)
        test_x = test[FEATURES].replace([np.inf, -np.inf], np.nan)
        medians = train_x.median()
        train_x = train_x.fillna(medians)
        test_x = test_x.fillna(medians)
        train_y = train[target].astype(int)
        test_y = test[target].astype(int)

        model = HistGradientBoostingClassifier(
            learning_rate=0.05,
            max_iter=180,
            max_leaf_nodes=25,
            min_samples_leaf=80,
            l2_regularization=3.0,
            random_state=42,
        )
        model.fit(train_x, train_y)
        probability = model.predict_proba(test_x)[:, 1]
        predicted = probability >= 0.5
        permutation = permutation_importance(
            model,
            test_x,
            test_y,
            scoring="roc_auc",
            n_repeats=5,
            random_state=42,
            n_jobs=-1,
        )
        importance = pd.DataFrame(
            {
                "feature": FEATURES,
                "importance": permutation.importances_mean,
                "importance_std": permutation.importances_std,
                "horizon_min": minutes,
            }
        ).sort_values("importance", ascending=False)
        importance_rows.append(importance)
        interactions = interaction_table(test, target, probability)
        interactions["horizon_min"] = minutes
        interaction_outputs.append(interactions)
        monday = monday_morning_table(test, probability, target)
        monday["horizon_min"] = minutes
        monday_outputs.append(monday)
        results[str(minutes)] = {
            "train_rows": int(len(train)),
            "test_rows": int(len(test)),
            "continuation_rate": float(test_y.mean()),
            "accuracy": float(accuracy_score(test_y, predicted)),
            "balanced_accuracy": float(balanced_accuracy_score(test_y, predicted)),
            "roc_auc": float(roc_auc_score(test_y, probability)),
            "confidence": confidence_table(test_y.to_numpy(), probability),
            "top_features": importance.head(15).to_dict(orient="records"),
        }
        prediction_output[f"actual_{minutes}m"] = test_y.reindex(
            prediction_output.index
        )
        prediction_output[f"prob_continue_{minutes}m"] = pd.Series(
            probability, index=test.index
        ).reindex(prediction_output.index)

    importance_all = pd.concat(importance_rows, ignore_index=True)
    interactions_all = pd.concat(interaction_outputs, ignore_index=True)
    monday_all = pd.concat(monday_outputs, ignore_index=True)
    monday_summary = aggregate_monday(monday_all)
    prediction_output.to_csv(args.predictions, compression="gzip", float_format="%.6f")
    importance_all.to_csv(
        args.predictions.with_name("MARKET_MAP_trend_termination_importance.csv"),
        index=False,
        float_format="%.6f",
    )
    interactions_all.to_csv(
        args.predictions.with_name("MARKET_MAP_trend_termination_interactions.csv"),
        index=False,
        float_format="%.6f",
    )
    monday_all.to_csv(
        args.predictions.with_name("MARKET_MAP_trend_termination_monday_morning.csv"),
        index=False,
        float_format="%.6f",
    )
    monday_summary.to_csv(
        args.predictions.with_name(
            "MARKET_MAP_trend_termination_monday_morning_summary.csv"
        ),
        index=False,
        float_format="%.6f",
    )
    args.metrics.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")

    summary = pd.DataFrame(
        [
            {
                "horizon_min": int(horizon),
                "test_rows": values["test_rows"],
                "continue_rate": values["continuation_rate"],
                "accuracy": values["accuracy"],
                "balanced_accuracy": values["balanced_accuracy"],
                "roc_auc": values["roc_auc"],
            }
            for horizon, values in results.items()
        ]
    )
    top_features = importance_all.groupby("horizon_min", group_keys=False).head(10)
    monday_display = monday_all.sort_values(
        ["horizon_min", "continuation_rate"], ascending=[True, False]
    )
    lines = [
        "# MARKET_MAP Trend-Termination Study: 2024 Q4",
        "",
        "This study asks whether an already-active bullish or bearish movement will",
        "continue or terminate. Development uses 2023 through September 30, 2024.",
        "The untouched three-month holdout is October 1 through December 31, 2024.",
        "",
        "## Event Definition",
        "",
        "- Active movement: trailing-hour BULL/BEAR direction, TREND or CHOP structure,",
        "  and absolute displacement of at least `0.75 x ATR14`.",
        "- Contiguous M5 rows with the same active direction are deduplicated to the",
        "  first observation of each movement episode.",
        "- Continuation: an additional favorable move of `max(2 pips, 0.75 x ATR14)`",
        "  occurs before an adverse retracement of `max(2 pips, 0.50 x ATR14)`.",
        "- Termination: the adverse retracement occurs first.",
        "- Ambiguous paths reaching neither boundary are excluded.",
        "",
        "## Holdout Performance",
        "",
        markdown(summary),
        "",
        "## Most Useful Features",
        "",
        markdown(top_features[["horizon_min", "feature", "importance", "importance_std"]]),
        "",
        "## Monday Morning 06:00-10:00 UTC",
        "",
        markdown(monday_summary),
        "",
        "Detailed strength-band breakdown:",
        "",
        markdown(monday_display),
        "",
        "## Interpretation",
        "",
        "- ROC AUC measures ranking skill, not certainty. A result near 0.50 has no",
        "  useful discrimination; 0.60-0.65 is modest filter value.",
        "- Strength alone cannot identify an exact top. Strong efficient trends can",
        "  continue, while extreme expansion plus declining velocity may signal ending.",
        "- Time should be treated as context interacting with strength and volatility,",
        "  not as a standalone directional prediction.",
        "- Monday-morning confidence intervals are wide because the quarter contains",
        "  only 56-58 independent decisive episodes. These figures are hypotheses for",
        "  another holdout, not threshold settings.",
        "- Adjacent M5 events overlap. Results describe state-filter quality, not a",
        "  sequence of independent trades. Episode deduplication reduces, but does not",
        "  eliminate, dependence between nearby market movements.",
    ]
    args.report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(summary.to_string(index=False))
    print("report:", args.report)


if __name__ == "__main__":
    main()
