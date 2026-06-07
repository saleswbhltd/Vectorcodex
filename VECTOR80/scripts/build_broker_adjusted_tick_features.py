#!/usr/bin/env python3
"""Build broker-domain M5 features from raw Dukascopy yearly tick archives."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = Path(
    "/home/cmake/VectorShared/research/dukascopy/EURUSD/2023_2024"
)
DEFAULT_CALIBRATION = Path("/home/cmake/VectorShared/research/tick_calibration.json")
DEFAULT_OUTPUT = Path(
    "/home/cmake/VectorShared/research/dukascopy/EURUSD/2023_2024/broker_adjusted"
)
PIP = 0.0001


def apply_calibration(values: pd.Series, calibration: dict) -> np.ndarray:
    source = np.asarray(calibration["duka_quantiles"], dtype=float)
    target = np.asarray(calibration["broker_quantiles"], dtype=float)
    numeric = values.to_numpy(dtype=float)
    mapped = np.interp(numeric, source, target)
    mapped[~np.isfinite(numeric)] = np.nan
    return mapped


def tick_features(ticks: pd.DataFrame) -> pd.DataFrame:
    ticks = ticks.sort_values("datetime").reset_index(drop=True)
    ticks["bar_time"] = ticks["datetime"].dt.floor("5min")
    ticks["spread_pips"] = (ticks["ask"] - ticks["bid"]) / PIP
    ticks["bid_up"] = ticks["bid"].diff().gt(0).astype(float)
    ticks["ask_down"] = ticks["ask"].diff().lt(0).astype(float)
    ticks["mid_change_pips"] = ticks["mid"].diff().abs() / PIP
    ticks["time_delta_ms"] = ticks["datetime"].diff().dt.total_seconds() * 1000.0

    grouped = ticks.groupby("bar_time", sort=True)
    size = grouped.size()
    position = grouped.cumcount()
    group_size = ticks["bar_time"].map(size)
    first_half = position < (group_size // 2)
    second_half = ~first_half
    valid_half = group_size >= 4

    ticks["velocity_first"] = ticks["mid_change_pips"].where(first_half & valid_half)
    ticks["velocity_second"] = ticks["mid_change_pips"].where(second_half & valid_half)
    high = grouped["mid"].transform("max")
    low = grouped["mid"].transform("min")
    ticks["near_high"] = ((high - ticks["mid"]) / PIP <= 1.0).astype(float)
    ticks["near_low"] = ((ticks["mid"] - low) / PIP <= 1.0).astype(float)

    features = grouped.agg(
        open=("mid", "first"),
        high=("mid", "max"),
        low=("mid", "min"),
        close=("mid", "last"),
        tick_count=("mid", "size"),
        bid_volume=("bid_vol", "sum"),
        ask_volume=("ask_vol", "sum"),
        median_tick_interval_ms=("time_delta_ms", "median"),
        max_tick_interval_ms=("time_delta_ms", "max"),
        spread_avg=("spread_pips", "mean"),
        spread_max=("spread_pips", "max"),
        bid_aggressor_pct=("bid_up", "mean"),
        ask_aggressor_pct=("ask_down", "mean"),
        tick_velocity_first_half=("velocity_first", "mean"),
        tick_velocity_second_half=("velocity_second", "mean"),
        ticks_at_high_pct=("near_high", "mean"),
        ticks_at_low_pct=("near_low", "mean"),
    )
    features["bid_aggressor_pct"] *= 100.0
    features["ask_aggressor_pct"] *= 100.0
    features["imbalance"] = (
        features["bid_aggressor_pct"] - features["ask_aggressor_pct"]
    )
    features["vel_ratio_2nd_to_1st"] = (
        features["tick_velocity_second_half"]
        / features["tick_velocity_first_half"].replace(0.0, np.nan)
    )
    first_mid = grouped["mid"].first()
    features["max_run_up_pips_intrabar"] = (features["high"] - first_mid) / PIP
    features["max_run_dn_pips_intrabar"] = (first_mid - features["low"]) / PIP
    features["ticks_at_high_pct"] *= 100.0
    features["ticks_at_low_pct"] *= 100.0
    features.index.name = "datetime"
    return features.reset_index()


def process_year(
    year: int, input_dir: Path, output_dir: Path, calibration: dict
) -> tuple[Path, dict]:
    parts = sorted(
        (input_dir / ".parts").glob(f"EURUSD_TICK_{year}*.csv.gz")
    )
    if not parts:
        raise FileNotFoundError(f"no monthly parts found for {year}")
    frames = []
    previous_tick = None
    for part in parts:
        print("  feature month:", part.name, flush=True)
        ticks = pd.read_csv(part, parse_dates=["datetime"])
        ticks["datetime"] = pd.to_datetime(ticks["datetime"], utc=True)
        first_bar = ticks["datetime"].min().floor("5min")
        if previous_tick is not None:
            ticks = pd.concat([previous_tick, ticks], ignore_index=True)
        month_features = tick_features(ticks)
        frames.append(month_features[month_features["datetime"] >= first_bar])
        previous_tick = ticks.tail(1).copy()
    raw = (
        pd.concat(frames, ignore_index=True)
        .sort_values("datetime")
        .drop_duplicates("datetime")
        .reset_index(drop=True)
    )
    calibrated = raw.copy()
    mapped_features = []
    for feature, mapping in calibration.items():
        if feature not in raw:
            continue
        calibrated[f"{feature}_duka"] = raw[feature]
        calibrated[feature] = apply_calibration(raw[feature], mapping)
        mapped_features.append(feature)

    calibrated["source"] = "DUKASCOPY_PRICE_ROBOFOREX_FEATURE_CALIBRATION"
    calibrated["calibration_version"] = "tick_calibration_2026-06-05"
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / f"EURUSD_M5_broker_adjusted_{year}.csv.gz"
    calibrated.to_csv(
        output,
        index=False,
        compression="gzip",
        float_format="%.6f",
        date_format="%Y-%m-%dT%H:%M:%S%z",
    )
    metadata = {
        "year": year,
        "source_tick_files": [str(path) for path in parts],
        "output": str(output),
        "rows": int(len(calibrated)),
        "start": calibrated["datetime"].min().isoformat(),
        "end": calibrated["datetime"].max().isoformat(),
        "mapped_features": mapped_features,
        "price_domain": "Dukascopy midpoint OHLC",
        "volume_domain": "Dukascopy quoted bid/ask volume, not calibrated",
        "feature_domain": "RoboForex ECN quantile-calibrated",
        "calibration_source_periods": [
            "2025-12",
            "2026-04 through 2026-06",
        ],
        "unmapped_fields": [
            "datetime",
            "open",
            "high",
            "low",
            "close",
            "bid_volume",
            "ask_volume",
        ],
        "projection_assumption": (
            "The Dukascopy-to-RoboForex feature relationship measured in the "
            "2025-2026 overlap is assumed stable when projected back to this year."
        ),
        "warning": (
            "This is not a historical RoboForex tick feed. It is a Dukascopy M5 "
            "price series with selected tick features mapped to the broker domain."
        ),
    }
    output.with_suffix(output.suffix + ".metadata.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )
    return output, metadata


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--calibration", type=Path, default=DEFAULT_CALIBRATION)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--years", type=int, nargs="+", default=[2023, 2024])
    args = parser.parse_args()

    calibration = json.loads(args.calibration.read_text(encoding="utf-8"))
    manifest = {
        "calibration": str(args.calibration),
        "years": [],
    }
    for year in args.years:
        print("year:", year)
        output, metadata = process_year(
            year, args.input_dir, args.output_dir, calibration
        )
        manifest["years"].append(metadata)
        print("  output:", output)
    manifest_path = args.output_dir / "BROKER_ADJUSTED_MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print("manifest:", manifest_path)


if __name__ == "__main__":
    main()
