#!/usr/bin/env python3
"""
Generate leakage-safe VECTOR80 scores for every eligible M5 candidate bar.

Models are trained only on the frozen development window ending 2026-02-28.
The requested scoring period is never used for target construction, fitting, or
feature imputation. The EA remains responsible for pivot detection, group
matching, cooldowns, position limits, and threshold enforcement.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from refresh_vector80_scores import (
    DEV_END,
    ENGINES,
    RESEARCH,
    ROOT,
    fit_engine_bundle,
)


DEFAULT_START = pd.Timestamp("2026-03-01")
DEFAULT_END = pd.Timestamp("2026-06-01 23:55:00")
DEFAULT_SCORE_OUT = ROOT / "generated" / "VECTOR80_model_scores_full_oos.csv"
DEFAULT_DIAGNOSTICS_OUT = ROOT / "generated" / "VECTOR80_model_scores_full_oos_diagnostics.csv"


def parse_time(value: str) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is not None:
        timestamp = timestamp.tz_localize(None)
    return timestamp


def prepare_scoring_features(
    end: pd.Timestamp,
    feats: list[str],
    fill_values: pd.Series,
    step64,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    panel = pd.read_csv(
        RESEARCH / "EURUSD_M5_FULL_PANEL.csv.gz",
        index_col=0,
        parse_dates=True,
    ).loc[:end].copy()
    pivots = pd.read_csv(RESEARCH / "zzlines_pivot_map_enriched.csv", parse_dates=["pivot_time"])
    panel = step64.add_sr_features(panel, pivots)
    panel = step64.add_temporal_features(panel)

    missing = [column for column in feats if column not in panel.columns]
    if missing:
        raise SystemExit(f"scoring panel is missing required features: {missing[:20]}")

    raw_X = panel[feats].replace([np.inf, -np.inf], np.nan)
    X = raw_X.fillna(fill_values).fillna(0.0)
    return panel, X


def generate_scores(
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if start <= DEV_END:
        raise SystemExit(
            f"scoring start {start} overlaps the development window ending {DEV_END}"
        )
    if end < start:
        raise SystemExit("scoring end must not be earlier than scoring start")

    fitted, feats, fill_values, step64, rules = fit_engine_bundle()
    panel, X = prepare_scoring_features(end, feats, fill_values, step64)
    window = (panel.index >= start) & (panel.index <= end)
    if not window.any():
        raise SystemExit(f"no panel bars found between {start} and {end}")

    frames = []
    for spec in ENGINES:
        eligible = step64.stage1_mask(panel, rules, [spec.label]) & window
        indices = np.flatnonzero(eligible)
        if not len(indices):
            continue
        scores = fitted[spec.engine_id].predict_proba(X.iloc[indices])[:, 1]
        bar_times = panel.index[indices]
        frames.append(
            pd.DataFrame(
                {
                    "bar_time": bar_times,
                    # The research panel and score CSV use the same reference
                    # time. MT5 applies InpScoreTimeShiftMin during lookup.
                    "time": bar_times,
                    "engine_id": spec.engine_id,
                    "score": scores,
                    "threshold": spec.threshold,
                    "passes_threshold": scores >= spec.threshold,
                }
            )
        )

    if not frames:
        raise SystemExit("no eligible candidate bars were generated")

    diagnostics = pd.concat(frames, ignore_index=True).sort_values(
        ["bar_time", "engine_id"]
    )
    scores = diagnostics[["time", "engine_id", "score"]].copy()
    scores["time"] = scores["time"].dt.strftime("%Y-%m-%d %H:%M:%S")
    return scores, diagnostics


def print_summary(diagnostics: pd.DataFrame) -> None:
    summary = diagnostics.groupby("engine_id", sort=False).agg(
        eligible_bars=("score", "size"),
        above_threshold=("passes_threshold", "sum"),
        max_score=("score", "max"),
        mean_score=("score", "mean"),
    )
    print(summary.to_string(float_format=lambda value: f"{value:.6f}"))
    print(f"\ntotal score rows: {len(diagnostics)}")
    print(f"total rows above threshold: {int(diagnostics['passes_threshold'].sum())}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=parse_time, default=DEFAULT_START)
    parser.add_argument("--end", type=parse_time, default=DEFAULT_END)
    parser.add_argument("--out", type=Path, default=DEFAULT_SCORE_OUT)
    parser.add_argument("--diagnostics-out", type=Path, default=DEFAULT_DIAGNOSTICS_OUT)
    args = parser.parse_args()

    scores, diagnostics = generate_scores(args.start, args.end)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.diagnostics_out.parent.mkdir(parents=True, exist_ok=True)
    scores.to_csv(args.out, index=False, float_format="%.6f")
    diagnostics.to_csv(args.diagnostics_out, index=False, float_format="%.6f")

    print_summary(diagnostics)
    print(f"score CSV: {args.out}")
    print(f"diagnostics CSV: {args.diagnostics_out}")


if __name__ == "__main__":
    main()
