#!/usr/bin/env python3
"""Build leakage-safe MARKET_MAP horizon targets from the calibrated M5 panel."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


DEFAULT_PANEL = Path("/home/cmake/VectorShared/research/EURUSD_M5_CALIBRATED_PANEL.csv.gz")
DEFAULT_OUT = Path(__file__).resolve().parents[1] / "generated" / "MARKET_MAP_training.csv.gz"
HORIZONS = (1, 3, 6, 12)
PIP = 0.0001


def forward_extreme(values: pd.Series, bars: int, operation: str) -> pd.Series:
    shifted = values.shift(-1)
    rolling = shifted.iloc[::-1].rolling(bars, min_periods=bars)
    result = rolling.max() if operation == "max" else rolling.min()
    return result.iloc[::-1]


def add_horizon_targets(panel: pd.DataFrame, flat_pips: float) -> pd.DataFrame:
    out = panel.copy()
    close = out["close"].astype(float)
    high = out["high"].astype(float)
    low = out["low"].astype(float)

    for bars in HORIZONS:
        minutes = bars * 5
        future_close = close.shift(-bars)
        future_high = forward_extreme(high, bars, "max")
        future_low = forward_extreme(low, bars, "min")
        ret = (future_close - close) / PIP
        out[f"target_return_{minutes}m_pips"] = ret
        out[f"target_mfe_{minutes}m_pips"] = (future_high - close) / PIP
        out[f"target_mae_{minutes}m_pips"] = (future_low - close) / PIP
        out[f"target_range_{minutes}m_pips"] = (future_high - future_low) / PIP
        out[f"target_direction_{minutes}m"] = np.select(
            [ret > flat_pips, ret < -flat_pips], [1, -1], default=0
        ).astype("int8")

    utc_day = out.index.normalize()
    day_close = close.groupby(utc_day).transform("last")
    day_high_after = high.groupby(utc_day, group_keys=False).apply(
        lambda value: value.shift(-1).iloc[::-1].cummax().iloc[::-1]
    )
    day_low_after = low.groupby(utc_day, group_keys=False).apply(
        lambda value: value.shift(-1).iloc[::-1].cummin().iloc[::-1]
    )
    rest_return = (day_close - close) / PIP
    out["target_return_rest_day_pips"] = rest_return
    out["target_mfe_rest_day_pips"] = (day_high_after - close) / PIP
    out["target_mae_rest_day_pips"] = (day_low_after - close) / PIP
    out["target_range_rest_day_pips"] = (day_high_after - day_low_after) / PIP
    out["target_direction_rest_day"] = np.select(
        [rest_return > flat_pips, rest_return < -flat_pips], [1, -1], default=0
    ).astype("int8")
    return out


def load_panel(path: Path) -> pd.DataFrame:
    panel = pd.read_csv(path, index_col=0, parse_dates=True)
    panel.index = pd.DatetimeIndex(panel.index)
    if panel.index.tz is not None:
        panel.index = panel.index.tz_convert("UTC").tz_localize(None)
    panel = panel.sort_index()
    if panel.index.has_duplicates:
        raise ValueError("calibrated panel contains duplicate UTC bars")
    required = {"open", "high", "low", "close"}
    missing = required - set(panel.columns)
    if missing:
        raise ValueError(f"calibrated panel missing columns: {sorted(missing)}")
    return panel


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--panel", type=Path, default=DEFAULT_PANEL)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--flat-pips", type=float, default=1.0)
    args = parser.parse_args()

    panel = load_panel(args.panel)
    training = add_horizon_targets(panel, args.flat_pips)
    target_columns = [name for name in training if name.startswith("target_")]
    training = training.dropna(subset=target_columns)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    training.to_csv(args.out, compression="gzip", float_format="%.6f")

    metadata = {
        "version": "0.1.0",
        "source": str(args.panel),
        "time_basis": "UTC",
        "broker_timezone": "Europe/Helsinki",
        "calibration": "Dukascopy tick features quantile-mapped to RoboForex ECN",
        "flat_pips": args.flat_pips,
        "rows": len(training),
        "start": str(training.index.min()),
        "end": str(training.index.max()),
        "horizons_minutes": [bars * 5 for bars in HORIZONS],
        "target_columns": target_columns,
    }
    metadata_path = args.out.with_suffix("").with_suffix(".metadata.json")
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(f"rows: {len(training):,}")
    print(f"range: {training.index.min()} -> {training.index.max()}")
    print(f"dataset: {args.out}")
    print(f"metadata: {metadata_path}")


if __name__ == "__main__":
    main()

