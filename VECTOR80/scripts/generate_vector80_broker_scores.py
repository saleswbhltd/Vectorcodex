#!/usr/bin/env python3
"""
Generate all-bar VECTOR80 scores from a broker tick export.

The models and missing-value fills are frozen from the development period.
Broker timestamps are shifted back by the configured amount because MT5 adds
InpScoreTimeShiftMin when matching the CSV.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from refresh_vector80_scores import (
    COMMON,
    ENGINES,
    ROOT,
    fit_engine_bundle,
    load_event_candidates,
    prepare_live_panel,
)


DEFAULT_EVENTS = COMMON / "VECTOR80_events.csv"
DEFAULT_OUT = ROOT / "generated" / "VECTOR80_model_scores_broker_all_bars.csv"
DEFAULT_DIAGNOSTICS = ROOT / "generated" / "VECTOR80_model_scores_broker_all_bars_diagnostics.csv"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticks", type=Path, default=None)
    parser.add_argument("--events", type=Path, default=DEFAULT_EVENTS)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--diagnostics-out", type=Path, default=DEFAULT_DIAGNOSTICS)
    parser.add_argument("--score-shift-min", type=int, default=180)
    parser.add_argument("--start", default=None, help="Optional broker-time lower bound")
    args = parser.parse_args()

    if args.ticks is None:
        exports = sorted(
            COMMON.glob("VECTOR80_BROKER_TICKS_EURUSD_*.csv"),
            key=lambda path: path.stat().st_mtime,
        )
        if not exports:
            raise SystemExit("no VECTOR80 broker tick export found in Common Files")
        args.ticks = exports[-1]
    print(f"tick export: {args.ticks}")

    events = load_event_candidates(args.events, None)
    fitted, feats, fill_values, _, _ = fit_engine_bundle()
    X = prepare_live_panel(args.ticks, events, feats, fill_values)
    if args.start:
        X = X.loc[pd.Timestamp(args.start):]
    if X.empty:
        raise SystemExit("broker panel contains no scoreable M5 bars")

    frames = []
    for spec in ENGINES:
        scores = fitted[spec.engine_id].predict_proba(X)[:, 1]
        frames.append(
            pd.DataFrame(
                {
                    "broker_bar_time": X.index,
                    "time": X.index - pd.Timedelta(minutes=args.score_shift_min),
                    "engine_id": spec.engine_id,
                    "score": scores,
                    "threshold": spec.threshold,
                    "passes_threshold": scores >= spec.threshold,
                }
            )
        )

    diagnostics = pd.concat(frames, ignore_index=True).sort_values(
        ["broker_bar_time", "engine_id"]
    )
    output = diagnostics[["time", "engine_id", "score"]].copy()
    output["time"] = output["time"].dt.strftime("%Y-%m-%d %H:%M:%S")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.diagnostics_out.parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(args.out, index=False, float_format="%.6f")
    diagnostics.to_csv(args.diagnostics_out, index=False, float_format="%.6f")

    latest = diagnostics["broker_bar_time"].max()
    print(f"broker bars: {X.index.min()} -> {latest}")
    print(f"score rows: {len(output)}")
    print(f"rows above threshold: {int(diagnostics['passes_threshold'].sum())}")
    print(f"score CSV: {args.out}")
    print(f"diagnostics CSV: {args.diagnostics_out}")


if __name__ == "__main__":
    main()
