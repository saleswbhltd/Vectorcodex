#!/usr/bin/env python3
"""Test compact MARKET_MAP indicator families by horizon and market segment."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PANEL = Path("/home/cmake/VectorShared/research/EURUSD_M5_CALIBRATED_PANEL.csv.gz")
DEFAULT_OUT = ROOT / "generated" / "MARKET_MAP_family_scan.csv"
DEFAULT_REPORT = ROOT / "generated" / "MARKET_MAP_FAMILY_REPORT.md"
PIP = 0.0001
HORIZONS = (1, 2, 3, 6, 12)

FAMILIES = {
    "H1_CONTEXT": [
        "h1_bb_pctB",
        "h1_rsi14",
        "h1_dist_24h_high_pips",
        "h1_dist_24h_low_pips",
        "h1_dist_ema50_pips",
    ],
    "M5_MOMENTUM": [
        "rsi14",
        "macd_hist",
        "dist_ema20_atr",
        "body_to_range",
        "velocity_3",
    ],
    "MICROSTRUCTURE": [
        "imbalance",
        "tick_velocity_first_half",
        "tick_velocity_second_half",
        "max_run_up_pips_intrabar",
        "max_run_dn_pips_intrabar",
        "ticks_at_high_pct",
        "ticks_at_low_pct",
    ],
    "VOLATILITY": [
        "atr_pct100",
        "atr_ratio_5_50",
        "bb_squeeze",
        "realized_vol_20",
        "range_z20",
    ],
    "H1_PLUS_M5": [
        "h1_bb_pctB",
        "h1_rsi14",
        "h1_dist_24h_high_pips",
        "h1_dist_24h_low_pips",
        "h1_dist_ema50_pips",
        "rsi14",
        "macd_hist",
        "dist_ema20_atr",
        "body_to_range",
        "velocity_3",
    ],
    "H1_PLUS_MICRO": [
        "h1_bb_pctB",
        "h1_rsi14",
        "h1_dist_24h_high_pips",
        "h1_dist_24h_low_pips",
        "h1_dist_ema50_pips",
        "imbalance",
        "tick_velocity_second_half",
        "max_run_up_pips_intrabar",
        "max_run_dn_pips_intrabar",
    ],
}


def causalize_panel(frame: pd.DataFrame) -> pd.DataFrame:
    """Lag H1 values to the last fully completed H1 candle."""
    out = frame.copy()
    h1_columns = [name for name in out.columns if name.startswith("h1_")]
    out[h1_columns] = out[h1_columns].shift(12)
    return out


def session(hour: pd.Series) -> pd.Series:
    return pd.cut(
        hour,
        bins=[-1, 6, 11, 16, 21, 23],
        labels=["ASIAN", "LONDON", "LONDON_NY", "NEW_YORK", "LATE"],
    ).astype(str)


def auc(y: np.ndarray, probability: np.ndarray) -> float:
    if len(y) < 200 or len(np.unique(y)) < 2:
        return float("nan")
    return float(roc_auc_score(y, probability))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--panel", type=Path, default=DEFAULT_PANEL)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--flat-pips", type=float, default=1.0)
    args = parser.parse_args()

    frame = pd.read_csv(args.panel, index_col=0, parse_dates=True).sort_index()
    if frame.index.tz is not None:
        frame.index = frame.index.tz_convert("UTC").tz_localize(None)
    frame = causalize_panel(frame)
    frame["session"] = session(frame.index.to_series().dt.hour)
    frame["vol_bucket"] = pd.cut(
        frame["atr_pct100"],
        bins=[-np.inf, 0.33, 0.67, np.inf],
        labels=["LOW", "NORMAL", "HIGH"],
    ).astype(str)

    train_mask = frame.index <= pd.Timestamp("2025-12-31 23:59:59")
    test_mask = frame.index >= pd.Timestamp("2026-03-01")
    rows = []
    for bars in HORIZONS:
        minutes = bars * 5
        future_return = (frame["close"].shift(-bars) - frame["close"]) / PIP
        usable = future_return.abs() > args.flat_pips
        train = train_mask & usable & future_return.notna()
        test = test_mask & usable & future_return.notna()
        y_train = (future_return[train] > 0).astype(int).to_numpy()
        y_test = (future_return[test] > 0).astype(int).to_numpy()

        for name, features in FAMILIES.items():
            model = make_pipeline(
                SimpleImputer(strategy="median"),
                StandardScaler(),
                LogisticRegression(
                    C=0.2,
                    class_weight="balanced",
                    max_iter=1000,
                    random_state=42,
                ),
            )
            model.fit(frame.loc[train, features], y_train)
            probability = model.predict_proba(frame.loc[test, features])[:, 1]
            test_rows = frame.loc[test, ["session", "vol_bucket"]].copy()
            test_rows["y"] = y_test
            test_rows["p"] = probability
            rows.append(
                {
                    "horizon_min": minutes,
                    "family": name,
                    "segment_type": "ALL",
                    "segment": "ALL",
                    "rows": len(test_rows),
                    "auc": auc(y_test, probability),
                }
            )
            for segment_type in ("session", "vol_bucket"):
                for segment, group in test_rows.groupby(segment_type):
                    rows.append(
                        {
                            "horizon_min": minutes,
                            "family": name,
                            "segment_type": segment_type.upper(),
                            "segment": segment,
                            "rows": len(group),
                            "auc": auc(group["y"].to_numpy(), group["p"].to_numpy()),
                        }
                    )

    results = pd.DataFrame(rows)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    results.to_csv(args.out, index=False, float_format="%.6f")

    overall = results[results["segment_type"] == "ALL"]
    lines = [
        "# MARKET_MAP Indicator Family Study",
        "",
        "Balanced logistic models are fitted through December 31, 2025 and tested",
        "from March 1 through June 1, 2026. Moves within 1 pip are excluded.",
        "",
        "## Overall AUC",
        "",
        "| Family | 5m | 10m | 15m | 30m | 60m |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for family in FAMILIES:
        values = overall[overall["family"] == family].set_index("horizon_min")["auc"]
        lines.append(
            f"| {family} | " + " | ".join(f"{values.get(h, np.nan):.3f}" for h in (5, 10, 15, 30, 60)) + " |"
        )

    lines.extend(["", "## Best Segments", ""])
    segmented = results[results["segment_type"] != "ALL"].dropna(subset=["auc"])
    for minutes in (5, 10, 15, 30, 60):
        lines.extend(
            [
                f"### {minutes} minutes",
                "",
                "| Family | Segment | Rows | AUC |",
                "|---|---|---:|---:|",
            ]
        )
        top = segmented[segmented["horizon_min"] == minutes].nlargest(10, "auc")
        for row in top.itertuples(index=False):
            lines.append(
                f"| {row.family} | {row.segment_type}:{row.segment} | "
                f"{row.rows:,} | {row.auc:.3f} |"
            )
        lines.append("")
    lines.extend(
        [
            "## Gate",
            "",
            "- A family needs overall AUC >= 0.55 and no major session collapse before further work.",
            "- Segment results are diagnostic and must not be used to create time filters without a second OOS period.",
            "- Models remain disconnected from live trading.",
        ]
    )
    args.report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"rows: {len(results):,}")
    print(f"results: {args.out}")
    print(f"report: {args.report}")


if __name__ == "__main__":
    main()
