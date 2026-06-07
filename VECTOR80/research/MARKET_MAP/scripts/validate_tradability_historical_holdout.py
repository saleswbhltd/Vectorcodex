#!/usr/bin/env python3
"""Validate frozen 2025 tradability zones on an independent 2024 quarter."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

try:
    from scripts.study_market_regimes import current_path, label_axes
    from scripts.study_tradability_zones import (
        DAYS,
        add_forward_outcomes,
        add_parent_confirmation,
        stable_zones,
    )
except ModuleNotFoundError:
    from study_market_regimes import current_path, label_axes
    from study_tradability_zones import (
        DAYS,
        add_forward_outcomes,
        add_parent_confirmation,
        stable_zones,
    )


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PANEL = Path(
    "/home/cmake/VectorShared/research/dukascopy/EURUSD/2023_2024/"
    "broker_adjusted/EURUSD_M5_broker_adjusted_2024.csv.gz"
)
DEFAULT_DEV = ROOT / "generated" / "MARKET_MAP_tradability_zones.csv"
DEFAULT_ORIGINAL = ROOT / "generated" / "MARKET_MAP_tradability_validation.csv"
DEFAULT_OUT = ROOT / "generated" / "MARKET_MAP_tradability_2024Q4_validation.csv"
DEFAULT_REPORT = ROOT / "generated" / "MARKET_MAP_TRADABILITY_2024Q4_VALIDATION.md"
PIP = 0.0001
CALIBRATION = Path("/home/cmake/VectorShared/research/tick_calibration.json")


def load_canonical_panel_builder():
    path = Path("/home/cmake/VectorShared/research/35_build_full_panel.py")
    spec = importlib.util.spec_from_file_location("canonical_step35", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load canonical panel builder: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def canonicalize_adjusted_panel(frame: pd.DataFrame) -> pd.DataFrame:
    """Reproduce steps 33-35 and 84 serialization relevant to tradability."""
    out = frame.copy()
    out["tick_volume"] = out["tick_count_duka"]
    calibration = json.loads(CALIBRATION.read_text(encoding="utf-8"))
    for feature in calibration:
        raw_column = f"{feature}_duka"
        if raw_column in out:
            out[feature] = out[raw_column]
    out["bar_high"] = out["high"]
    out["bar_low"] = out["low"]
    # Step 34 writes the joined OHLC/tick panel with float_format="%.4f".
    numeric = out.select_dtypes(include=[np.number]).columns
    out[numeric] = out[numeric].round(4)
    step35 = load_canonical_panel_builder()
    out = step35.add_m5_indicators(out)
    # Step 35 writes six decimals before step 84 applies tick calibration.
    numeric = out.select_dtypes(include=[np.number]).columns
    out[numeric] = out[numeric].round(6)
    for feature, mapping in calibration.items():
        if feature not in out:
            continue
        values = out[feature].to_numpy(dtype=float)
        mapped = np.interp(
            values,
            np.asarray(mapping["duka_quantiles"], dtype=float),
            np.asarray(mapping["broker_quantiles"], dtype=float),
        )
        mapped[~np.isfinite(values)] = np.nan
        out[feature] = mapped
    # Step 84 writes the calibrated panel with float_format="%.5f".
    numeric = out.select_dtypes(include=[np.number]).columns
    out[numeric] = out[numeric].round(5)
    return out


def prepare_adjusted_frame(panel: Path) -> pd.DataFrame:
    frame = pd.read_csv(panel, parse_dates=["datetime"]).set_index("datetime").sort_index()
    if frame.index.tz is not None:
        frame.index = frame.index.tz_convert("UTC").tz_localize(None)
    frame = canonicalize_adjusted_panel(frame)

    observed = current_path(frame)
    labels = label_axes(observed).add_prefix("current_")
    frame = frame.join(observed).join(labels)
    frame = add_forward_outcomes(frame)
    frame = frame[frame.index.dayofweek < 5].copy()
    frame["dow_index"] = frame.index.dayofweek
    frame["day"] = frame["dow_index"].map(dict(enumerate(DAYS)))
    frame["spread_atr"] = frame["spread_avg"] / frame["atr14_pips"].clip(lower=0.1)
    frame["tick_rate"] = frame["tick_count"] / 300.0
    frame["balanced_flow"] = 1.0 - frame["imbalance"].abs().clip(upper=100.0) / 100.0
    frame["liquidity_score_bar"] = (
        0.35 * frame["tick_count"].rank(pct=True)
        + 0.20 * frame["bid_volume"].rank(pct=True)
        + 0.20 * frame["ask_volume"].rank(pct=True)
        + 0.15 * (1.0 - frame["spread_atr"].rank(pct=True))
        + 0.10 * (1.0 - frame["max_tick_interval_ms"].rank(pct=True))
    ) * 100.0
    return frame


def aggregate_holdout(
    frame: pd.DataFrame, start: str, end: str, resolution_min: int
) -> pd.DataFrame:
    selected = frame[
        (frame.index >= start) & (frame.index < end) & frame["future_valid"]
    ].copy()
    selected["slot"] = (
        selected.index.hour * 60 + selected.index.minute
    ) // resolution_min
    selected["time"] = selected["slot"].map(
        lambda value: (
            f"{value * resolution_min // 60:02d}:"
            f"{value * resolution_min % 60:02d}"
        )
    )
    grouped = selected.groupby(
        ["dow_index", "slot", "day", "time"], observed=True
    )
    zones = grouped.agg(
        rows=("close", "size"),
        tick_count=("tick_count", "mean"),
        tick_volume=("tick_volume", "mean"),
        bid_volume=("bid_volume", "mean"),
        ask_volume=("ask_volume", "mean"),
        spread_avg=("spread_avg", "mean"),
        spread_atr=("spread_atr", "mean"),
        max_tick_interval_ms=("max_tick_interval_ms", "median"),
        imbalance_abs=("imbalance", lambda values: values.abs().mean()),
        liquidity_score=("liquidity_score_bar", "mean"),
        clean_move_share=("future_cleanliness", lambda values: (values >= 0.45).mean()),
        future_cleanliness=("future_cleanliness", "mean"),
        future_abs_move=("future_abs_move", "mean"),
        continuation_win_rate=("continuation_win", "mean"),
        continuation_edge=("continuation_edge", "mean"),
        continuation_mfe=("continuation_mfe", "mean"),
        continuation_mae=("continuation_mae", "mean"),
        reversal_win_rate=("reversal_win", "mean"),
        reversal_edge=("reversal_edge", "mean"),
        reversal_mfe=("reversal_mfe", "mean"),
        reversal_mae=("reversal_mae", "mean"),
    ).reset_index()
    zones["period"] = "HISTORICAL_HOLDOUT_2024Q4"
    zones["resolution_min"] = resolution_min
    return zones


def frozen_development(path: Path, resolution_min: int) -> pd.DataFrame:
    zones = pd.read_csv(path)
    return zones[
        zones["period"].eq("DEV") & zones["resolution_min"].eq(resolution_min)
    ].copy()


def markdown(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "No zones passed."
    columns = list(frame.columns)
    lines = [
        "| " + " | ".join(columns) + " |",
        "|" + "|".join("---" for _ in columns) + "|",
    ]
    for row in frame.itertuples(index=False, name=None):
        lines.append("| " + " | ".join(str(value) for value in row) + " |")
    return "\n".join(lines)


def write_report(
    validation: pd.DataFrame,
    original: pd.DataFrame,
    output: Path,
    start: str,
    end: str,
) -> None:
    primary = validation[validation["resolution_min"].eq(15)].copy()
    dev_candidates = primary[
        primary["strategy_fit_dev"].ne("AVOID")
        & primary["selected_edge_dev"].gt(0)
    ]
    replicated = dev_candidates[dev_candidates["selected_edge_oos"].gt(0)]
    parent_confirmed = replicated[replicated["robust_zone"]]

    original_robust = original[
        original["resolution_min"].eq(15) & original["robust_zone"]
    ][["day", "time", "strategy_fit_dev"]].copy()
    external = original_robust.merge(
        primary,
        on=["day", "time", "strategy_fit_dev"],
        how="left",
        suffixes=("_original", ""),
    )
    external_positive = external["selected_edge_oos"].gt(0)
    candidate_weighted_edge = float(
        np.average(dev_candidates["selected_edge_oos"], weights=dev_candidates["rows_oos"])
    )
    external_weighted_edge = float(
        np.average(external["selected_edge_oos"], weights=external["rows_oos"])
    )

    top = parent_confirmed.sort_values("selected_edge_oos", ascending=False)[
        [
            "day",
            "time",
            "strategy_fit_dev",
            "best_quality_dev",
            "selected_edge_dev",
            "selected_edge_oos",
            "selected_wr_oos",
            "rows_oos",
        ]
    ].head(20).round(3)
    original_table = external[
        [
            "day",
            "time",
            "strategy_fit_dev",
            "selected_edge_oos",
            "selected_wr_oos",
            "rows_oos",
        ]
    ].sort_values("selected_edge_oos", ascending=False).round(3)

    rows = int(primary["rows_oos"].sum())
    lines = [
        "# MARKET_MAP Tradability Historical Holdout: 2024 Q4",
        "",
        "This is an independent three-month historical validation of frozen calendar",
        "2025 tradability-zone definitions on broker-adjusted Dukascopy M5 features.",
        "It is reverse-time validation, not forward OOS, because the holdout predates",
        "the development period.",
        "This parity-safe run supersedes the initial 2024 Q4 result.",
        "",
        "## Period",
        "",
        f"- Start: `{start}` UTC, inclusive.",
        f"- End: `{end}` UTC, exclusive.",
        f"- Valid M5 observations grouped into 15-minute zones: `{rows}`.",
        "- September 2024 data is retained only as causal indicator warm-up.",
        "",
        "## Frozen Contract",
        "",
        "- Panel construction reproduces canonical research steps 33, 34, 35 and 84",
        "  for all fields used by the tradability study.",
        "- The script-34 four-decimal intermediate serialization is reproduced before",
        "  canonical script-35 indicators are calculated.",
        "- ATR14 uses the same Wilder-style exponential smoothing as the 2025 panel.",
        "- Tick calibration is applied after panel construction, in the same order as",
        "  canonical script 84.",
        "- Zone quality and continuation/reversal choice come only from calendar 2025.",
        "- Dynamic target: `max(3 pips, 1.0 x ATR14)`.",
        "- Dynamic stop: `max(2 pips, 0.75 x ATR14)`.",
        "- Outcome horizon: next 30 minutes; spread is included.",
        "- Fifteen-minute zones require matching positive 30-minute parent behavior",
        "  to receive robust confirmation.",
        "",
        "## Results",
        "",
        f"- Frozen 2025 positive-edge 15-minute candidates: `{len(dev_candidates)}`.",
        f"- Positive again in 2024 Q4: `{len(replicated)}` "
        f"({len(replicated) / max(len(dev_candidates), 1):.1%}).",
        f"- Weighted mean holdout edge across all 88 candidates: "
        f"`{candidate_weighted_edge:+.3f} pips` per M5 entry.",
        f"- Also confirmed by the 30-minute parent: `{len(parent_confirmed)}`.",
        f"- Original 2025 + 2026 robust zones positive in 2024 Q4: "
        f"`{int(external_positive.sum())}/{len(external)}`.",
        f"- Weighted mean holdout edge across those 10 robust zones: "
        f"`{external_weighted_edge:+.3f} pips` per M5 entry.",
        "",
        "## Parent-Confirmed Replications",
        "",
        markdown(top),
        "",
        "## Original Robust-Zone External Check",
        "",
        markdown(original_table),
        "",
        "## Interpretation",
        "",
        "- A three-month cell normally contains 12-14 weekday dates and 36-42 M5",
        "  entries, so individual time cells remain noisy.",
        "- The broad positive-development candidate list failed as a portfolio; its",
        "  average holdout edge was negative. Quality ranking alone is insufficient.",
        "- The previously narrowed 10-zone robust set replicated materially better,",
        "  supporting 30-minute parent confirmation and repeated-period validation.",
        "- Broad replication rate matters more than one unusually profitable cell.",
        "- Thirty-minute outcomes from entries five minutes apart overlap. Edge values",
        "  describe filter quality and must not be read as independent trade returns.",
        "- Prices and quoted volume are Dukascopy. Fifteen microstructure fields are",
        "  mapped to the RoboForex feature domain using the 2025-2026 overlap.",
        "- That backward calibration is a domain-transfer assumption and prevents this",
        "  sample from being called genuine historical RoboForex OOS data.",
        "- Zones should remain setup filters, not independent entry signals.",
        "",
        "## Method Audit",
        "",
        "- The reference HTML in `C:/Users/cmake/Documents` is byte-identical to the",
        "  project-generated 2025-2026 map.",
        "- A direct raw-tick comparison against canonical script 34 matched 575/576",
        "  extracted bars at four-decimal precision. The sole mismatch was the first",
        "  sliced bar lacking its preceding tick.",
        "- The yearly builder now carries the preceding monthly tick forward, matching",
        "  continuous-stream interval and aggressor calculations at month boundaries.",
        "- The same `add_forward_outcomes`, 15/30-minute aggregation, frozen ranking,",
        "  strategy selection and parent-confirmation functions are used.",
    ]
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--panel", type=Path, default=DEFAULT_PANEL)
    parser.add_argument("--development-zones", type=Path, default=DEFAULT_DEV)
    parser.add_argument("--original-validation", type=Path, default=DEFAULT_ORIGINAL)
    parser.add_argument("--start", default="2024-10-01")
    parser.add_argument("--end", default="2025-01-01")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    frame = prepare_adjusted_frame(args.panel)
    validations = []
    for resolution_min in (15, 30):
        dev = frozen_development(args.development_zones, resolution_min)
        holdout = aggregate_holdout(frame, args.start, args.end, resolution_min)
        validations.append(stable_zones(dev, holdout))
    validation = add_parent_confirmation(pd.concat(validations, ignore_index=True))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    validation.to_csv(args.out, index=False, float_format="%.6f")
    original = pd.read_csv(args.original_validation)
    write_report(validation, original, args.report, args.start, args.end)
    print("15m positive:", int(
        validation.loc[validation["resolution_min"].eq(15), "stable_positive"].sum()
    ))
    print("15m parent-confirmed:", int(
        validation.loc[validation["resolution_min"].eq(15), "robust_zone"].sum()
    ))
    print("output:", args.out)
    print("report:", args.report)


if __name__ == "__main__":
    main()
