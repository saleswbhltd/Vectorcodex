#!/usr/bin/env python3
"""Time normalization helpers for broker and Dukascopy MARKET_MAP data."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from scipy.stats import spearmanr


BROKER_TIMEZONE = "Europe/Helsinki"
PIP = 0.0001


@dataclass(frozen=True)
class AlignmentResult:
    shift_hours: int
    bars: int
    range_spearman: float
    return_spearman: float

    @property
    def passed(self) -> bool:
        return self.bars >= 500 and self.return_spearman >= 0.90


def broker_server_to_utc(values: pd.Series | pd.DatetimeIndex) -> pd.DatetimeIndex:
    """
    Convert naive RoboForex EET/EEST server timestamps to naive UTC.

    Europe/Helsinki supplies the exact EU DST transition dates. ``ambiguous``
    inference handles the repeated autumn hour when a chronological tick
    sequence contains both occurrences.
    """
    index = pd.DatetimeIndex(pd.to_datetime(values))
    if index.tz is not None:
        return index.tz_convert("UTC").tz_localize(None)
    localized = index.tz_localize(
        BROKER_TIMEZONE,
        ambiguous="infer",
        nonexistent="raise",
    )
    return localized.tz_convert("UTC").tz_localize(None)


def normalize_broker_ticks(frame: pd.DataFrame) -> pd.DataFrame:
    """Return broker ticks indexed by verified UTC timestamps."""
    required = {"datetime", "time_msc"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"broker tick frame missing columns: {sorted(missing)}")

    out = frame.copy()
    server_time = pd.to_datetime(out["datetime"])
    encoded_time = pd.to_datetime(out["time_msc"], unit="ms", utc=True).dt.tz_localize(None)
    delta_ms = (server_time - encoded_time).dt.total_seconds().abs() * 1000
    if delta_ms.quantile(0.999) > 1100:
        raise ValueError("datetime and time_msc do not describe the same broker clock")

    out["broker_time"] = server_time
    out["datetime"] = broker_server_to_utc(server_time)
    out["broker_utc_offset_hours"] = (
        (out["broker_time"] - out["datetime"]).dt.total_seconds() / 3600
    ).astype("int8")
    return out.sort_values("datetime").reset_index(drop=True)


def load_broker_ticks(path: Path) -> pd.DataFrame:
    return normalize_broker_ticks(pd.read_csv(path))


def m5_mid_bars(ticks: pd.DataFrame) -> pd.DataFrame:
    frame = ticks.copy()
    if "mid" not in frame:
        frame["mid"] = (frame["bid"] + frame["ask"]) * 0.5
    return (
        frame.set_index("datetime")["mid"]
        .resample("5min")
        .ohlc()
        .dropna()
    )


def score_alignment(
    broker_bars: pd.DataFrame,
    dukascopy_bars: pd.DataFrame,
    shift_hours: int = 0,
) -> AlignmentResult:
    broker = broker_bars.copy()
    broker.index = pd.DatetimeIndex(broker.index) + pd.Timedelta(hours=shift_hours)
    duka = dukascopy_bars.copy()
    duka.index = pd.DatetimeIndex(duka.index)
    if duka.index.tz is not None:
        duka.index = duka.index.tz_convert("UTC").tz_localize(None)

    common = broker.index.intersection(duka.index)
    if len(common) < 2:
        return AlignmentResult(shift_hours, len(common), float("nan"), float("nan"))

    broker_range = (broker.loc[common, "high"] - broker.loc[common, "low"]) / PIP
    duka_range = (duka.loc[common, "high"] - duka.loc[common, "low"]) / PIP
    range_rho = float(spearmanr(broker_range, duka_range, nan_policy="omit").statistic)

    broker_returns = broker.loc[common, "close"].diff()
    duka_returns = duka.loc[common, "close"].diff()
    return_rho = float(
        spearmanr(broker_returns, duka_returns, nan_policy="omit").statistic
    )
    return AlignmentResult(shift_hours, len(common), range_rho, return_rho)


def require_alignment(result: AlignmentResult) -> None:
    if not result.passed:
        raise RuntimeError(
            "broker/Dukascopy alignment failed: "
            f"bars={result.bars} return_rho={result.return_spearman:.4f}"
        )

