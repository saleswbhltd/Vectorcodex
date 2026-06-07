#!/usr/bin/env python3
"""Out-of-sample indicator scan for MARKET_MAP state and forecast horizons."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.metrics import roc_auc_score


DEFAULT_PANEL = Path("/home/cmake/VectorShared/research/EURUSD_M5_CALIBRATED_PANEL.csv.gz")
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "generated" / "MARKET_MAP_indicator_scan.csv"
DEFAULT_REPORT = ROOT / "generated" / "MARKET_MAP_INDICATOR_REPORT.md"
PIP = 0.0001
HORIZONS = (1, 2, 3, 6, 12)

EXCLUDED = {
    "open",
    "high",
    "low",
    "close",
    "bar_high",
    "bar_low",
    "ema20",
    "ema50",
    "ema200",
    "tick_volume",
    "bid_volume",
    "ask_volume",
}

FAMILIES = {
    "trend": {
        "dist_ema20_atr", "dist_ema50_atr", "adx14", "plus_di", "minus_di",
        "h1_ema50_slope_pips", "h1_ema200_slope_pips", "h1_dist_ema50_pips",
        "h1_dist_ema200_pips", "h1_trend_dir",
    },
    "momentum": {
        "rsi14", "stoch_k", "stoch_d", "macd", "macd_sig", "macd_hist",
        "williams_r14", "velocity_3", "accel", "consec_up", "consec_dn",
        "h1_rsi14", "h1_bb_pctB",
    },
    "volatility": {
        "atr5", "atr14_pips", "atr50", "atr_ratio_5_50", "atr_pct100",
        "bb_width_pips", "bb_squeeze", "realized_vol_20", "range_pips",
        "range_z20", "vol_of_vol_20", "h1_atr14_pips",
    },
    "candle": {
        "body_pips", "body_to_range", "upper_wick_ratio", "lower_wick_ratio",
        "bb_pctB",
    },
    "microstructure": {
        "tick_count", "median_tick_interval_ms", "max_tick_interval_ms",
        "spread_avg", "spread_max", "bid_aggressor_pct", "ask_aggressor_pct",
        "imbalance", "tick_velocity_first_half", "tick_velocity_second_half",
        "vel_ratio_2nd_to_1st", "max_run_up_pips_intrabar",
        "max_run_dn_pips_intrabar", "ticks_at_high_pct", "ticks_at_low_pct",
    },
    "location": {
        "dist_to_5bar_high_pips", "dist_to_5bar_low_pips",
        "dist_to_20bar_high_pips", "dist_to_20bar_low_pips",
        "dist_to_50bar_high_pips", "dist_to_50bar_low_pips",
        "dist_to_today_high_pips", "dist_to_today_low_pips",
        "h1_dist_24h_high_pips", "h1_dist_24h_low_pips",
    },
    "time": {"hour_utc", "dow"},
}


def family_of(feature: str) -> str:
    for family, names in FAMILIES.items():
        if feature in names:
            return family
    return "other"


def causalize_panel(frame: pd.DataFrame) -> pd.DataFrame:
    """Lag H1 values to the last fully completed H1 candle."""
    out = frame.copy()
    h1_columns = [name for name in out.columns if name.startswith("h1_")]
    out[h1_columns] = out[h1_columns].shift(12)
    return out


def safe_spearman(left: pd.Series, right: pd.Series) -> float:
    mask = left.notna() & right.notna()
    if mask.sum() < 100 or left[mask].nunique() < 2:
        return float("nan")
    return float(spearmanr(left[mask], right[mask]).statistic)


def build_targets(frame: pd.DataFrame) -> pd.DataFrame:
    close = frame["close"].astype(float)
    high = frame["high"].astype(float)
    low = frame["low"].astype(float)
    out = pd.DataFrame(index=frame.index)
    for bars in HORIZONS:
        minutes = bars * 5
        out[f"return_{minutes}m"] = (close.shift(-bars) - close) / PIP

    prior_close = close.shift(12)
    out["state_direction"] = (close - prior_close) / (frame["atr14_pips"] * PIP)
    path = close.diff().abs().rolling(12).sum()
    out["state_efficiency"] = (close - prior_close).abs() / path.replace(0, np.nan)
    out["state_volatility"] = frame["atr_pct100"]
    out["state_chop"] = 1.0 - out["state_efficiency"]
    out["state_pressure"] = (
        frame["body_to_range"].clip(-1, 1) * 0.5
        + (frame["plus_di"] - frame["minus_di"]).clip(-50, 50) / 100.0
    )
    return out


def forecast_metrics(
    dev_feature: pd.Series,
    dev_return: pd.Series,
    test_feature: pd.Series,
    test_return: pd.Series,
    flat_pips: float,
) -> dict[str, float]:
    dev_ic = safe_spearman(dev_feature, dev_return)
    orientation = 1.0 if np.isnan(dev_ic) or dev_ic >= 0 else -1.0
    oriented = test_feature * orientation
    test_ic = safe_spearman(oriented, test_return)

    mask = oriented.notna() & test_return.notna() & (test_return.abs() > flat_pips)
    auc = float("nan")
    if mask.sum() >= 200 and oriented[mask].nunique() >= 2:
        auc = float(roc_auc_score((test_return[mask] > 0).astype(int), oriented[mask]))

    valid = pd.DataFrame({"x": oriented, "ret": test_return}).dropna()
    spread = top_hit = bottom_hit = float("nan")
    if len(valid) >= 1000 and valid["x"].nunique() >= 10:
        low, high = valid["x"].quantile([0.1, 0.9])
        bottom = valid[valid["x"] <= low]["ret"]
        top = valid[valid["x"] >= high]["ret"]
        spread = float(top.mean() - bottom.mean())
        top_hit = float((top > flat_pips).mean())
        bottom_hit = float((bottom < -flat_pips).mean())

    return {
        "dev_ic": dev_ic,
        "orientation": orientation,
        "test_ic": test_ic,
        "auc": auc,
        "decile_spread_pips": spread,
        "top_up_hit": top_hit,
        "bottom_down_hit": bottom_hit,
        "sign_stable": bool(not np.isnan(dev_ic) and not np.isnan(test_ic) and test_ic >= 0),
    }


def scan(panel: pd.DataFrame, flat_pips: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    targets = build_targets(panel)
    dev_mask = panel.index <= pd.Timestamp("2025-12-31 23:59:59")
    test_mask = panel.index >= pd.Timestamp("2026-03-01")
    numeric = panel.select_dtypes(include=[np.number, "bool"])
    features = [
        name for name in numeric.columns
        if name not in EXCLUDED
        and numeric[name].nunique(dropna=True) >= 5
        and numeric[name].isna().mean() < 0.20
    ]

    forecast_rows = []
    state_rows = []
    for feature in features:
        family = family_of(feature)
        series = numeric[feature].replace([np.inf, -np.inf], np.nan)
        state_rows.append(
            {
                "indicator": feature,
                "family": family,
                "direction_corr": safe_spearman(series[test_mask], targets.loc[test_mask, "state_direction"]),
                "efficiency_corr": safe_spearman(series[test_mask], targets.loc[test_mask, "state_efficiency"]),
                "volatility_corr": safe_spearman(series[test_mask], targets.loc[test_mask, "state_volatility"]),
                "chop_corr": safe_spearman(series[test_mask], targets.loc[test_mask, "state_chop"]),
                "pressure_corr": safe_spearman(series[test_mask], targets.loc[test_mask, "state_pressure"]),
            }
        )
        for bars in HORIZONS:
            minutes = bars * 5
            target = targets[f"return_{minutes}m"]
            values = forecast_metrics(
                series[dev_mask],
                target[dev_mask],
                series[test_mask],
                target[test_mask],
                flat_pips,
            )
            forecast_rows.append(
                {
                    "indicator": feature,
                    "family": family,
                    "horizon_min": minutes,
                    **values,
                }
            )
    return pd.DataFrame(forecast_rows), pd.DataFrame(state_rows)


def report(forecast: pd.DataFrame, state: pd.DataFrame) -> str:
    lines = [
        "# MARKET_MAP Indicator Study",
        "",
        "Indicators are oriented using data through December 31, 2025 and evaluated",
        "on March 1 through June 1, 2026. Flat moves within 1 pip are excluded from AUC.",
        "",
        "## Current State",
        "",
    ]
    state_metrics = [
        ("Direction", "direction_corr"),
        ("Trend efficiency", "efficiency_corr"),
        ("Volatility", "volatility_corr"),
        ("Chop", "chop_corr"),
        ("Pressure", "pressure_corr"),
    ]
    for title, metric in state_metrics:
        lines.extend([f"### {title}", "", "| Indicator | Family | |rho| | Signed rho |", "|---|---|---:|---:|"])
        top = state.assign(rank=state[metric].abs()).nlargest(10, "rank")
        for row in top.itertuples(index=False):
            value = getattr(row, metric)
            lines.append(f"| `{row.indicator}` | {row.family} | {abs(value):.3f} | {value:.3f} |")
        lines.append("")

    lines.extend(["## Future Direction", ""])
    for horizon in HORIZONS:
        minutes = horizon * 5
        lines.extend(
            [
                f"### {minutes} minutes",
                "",
                "| Indicator | Family | Test IC | AUC | Decile spread (pips) | Stable |",
                "|---|---|---:|---:|---:|---:|",
            ]
        )
        subset = forecast[forecast["horizon_min"] == minutes].copy()
        subset["rank"] = (
            subset["test_ic"].clip(lower=0).fillna(0) * 0.45
            + (subset["auc"].fillna(0.5) - 0.5).clip(lower=0) * 0.8
            + subset["decile_spread_pips"].clip(lower=0).fillna(0) / 20.0
        )
        top = subset.sort_values(["sign_stable", "rank"], ascending=False).head(12)
        for row in top.itertuples(index=False):
            lines.append(
                f"| `{row.indicator}` | {row.family} | {row.test_ic:.3f} | "
                f"{row.auc:.3f} | {row.decile_spread_pips:.2f} | "
                f"{'yes' if row.sign_stable else 'no'} |"
            )
        lines.append("")
    lines.extend(
        [
            "## Interpretation Rules",
            "",
            "- An indicator is not accepted from AUC alone.",
            "- Direction must be stable from development to test.",
            "- Prefer indicators with positive test IC and positive extreme-bucket spread.",
            "- Correlated variants from one family count as one idea, not multiple confirmations.",
            "- This report measures prediction, not trade profitability after spread and commission.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--panel", type=Path, default=DEFAULT_PANEL)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--flat-pips", type=float, default=1.0)
    args = parser.parse_args()

    panel = pd.read_csv(args.panel, index_col=0, parse_dates=True).sort_index()
    if panel.index.tz is not None:
        panel.index = panel.index.tz_convert("UTC").tz_localize(None)
    panel = causalize_panel(panel)
    forecast, state = scan(panel, args.flat_pips)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    forecast.to_csv(args.out, index=False, float_format="%.6f")
    state_path = args.out.with_name("MARKET_MAP_state_indicator_scan.csv")
    state.to_csv(state_path, index=False, float_format="%.6f")
    args.report.write_text(report(forecast, state), encoding="utf-8")
    print(f"forecast rows: {len(forecast):,}")
    print(f"state rows: {len(state):,}")
    print(f"forecast: {args.out}")
    print(f"state: {state_path}")
    print(f"report: {args.report}")


if __name__ == "__main__":
    main()
