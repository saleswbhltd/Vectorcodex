#!/usr/bin/env python3
"""Render annual tradability data with the original 2025 map renderer."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

try:
    from scripts.study_tradability_zones import html_document
except ModuleNotFoundError:
    from study_tradability_zones import html_document


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ZONES = ROOT / "generated" / "MARKET_MAP_tradability_yearly_zones.csv"


def original_renderer_schema(zones: pd.DataFrame, year: int) -> pd.DataFrame:
    annual = zones[
        zones["year"].eq(year) & zones["resolution_min"].eq(15)
    ].copy()
    mapped = pd.DataFrame(
        {
            "day": annual["day"],
            "time": annual["time"],
            "strategy_fit_dev": annual["strategy_fit"],
            "best_quality_dev": annual["best_quality"],
            "liquidity_score_dev": annual["liquidity_score"],
            "tick_count_dev": annual["tick_count"],
            "tick_volume_dev": annual["tick_volume"],
            "bid_volume_dev": annual["bid_volume"],
            "ask_volume_dev": annual["ask_volume"],
            "spread_avg_dev": annual["spread_avg"],
            "spread_atr_dev": annual["spread_atr"],
            "future_cleanliness_dev": annual["future_cleanliness"],
            "continuation_edge_dev": annual["continuation_edge"],
            "continuation_edge_oos": annual["continuation_edge"],
            "reversal_edge_dev": annual["reversal_edge"],
            "reversal_edge_oos": annual["reversal_edge"],
            "selected_edge_dev": annual["selected_edge"],
            "selected_edge_oos": annual["selected_edge"],
            "selected_wr_oos": annual["selected_win_rate"],
            "stable_positive": annual["positive_zone"],
            "rows_dev": annual["rows"],
            "rows_oos": annual["rows"],
            "parent_30m_positive": annual["parent_30m_positive"],
            "parent_30m_strategy": annual["parent_30m_strategy"],
            "robust_zone": annual["parent_confirmed"],
            "resolution_min": annual["resolution_min"],
        }
    )
    return mapped


def annual_html(zones: pd.DataFrame, year: int) -> str:
    html = html_document(original_renderer_schema(zones, year))
    html = html.replace(
        "<title>EURUSD Advanced Tradability Zones</title>",
        f"<title>EURUSD Advanced Tradability Zones {year}</title>",
    )
    html = html.replace(
        "<h1>EURUSD Advanced Tradability Zones</h1>",
        f"<h1>EURUSD Advanced Tradability Zones {year}</h1>",
    )
    old_note = (
        "Each 15-minute weekday zone is ranked on liquidity, clean movement and "
        "target-before-stop performance.\n"
        "Bright green cells remained positive in March-June 2026 and have a "
        "positive 30-minute parent with the same strategy.\n"
        "Amber cells are positive at 15 minutes but lack 30-minute confirmation.\n"
        "The 30-minute aggregation is retained in the research table as a "
        "robustness check.\n"
        "Red zones failed OOS or are historical avoid zones. This is more specific "
        "than session filtering."
    )
    new_note = (
        "Each 15-minute weekday zone is ranked on liquidity, clean movement and "
        f"target-before-stop performance using calendar {year}.\n"
        "Bright green cells are positive and have a positive 30-minute parent with "
        "the same strategy.\n"
        "Amber cells are positive at 15 minutes but lack 30-minute confirmation.\n"
        "The 30-minute aggregation is retained as a confirmation layer.\n"
        "Red zones are negative or historical avoid zones. This is an annual "
        "descriptive map, not an OOS validation."
    )
    html = html.replace(old_note, new_note)
    html = html.replace("2025 quality:", f"{year} quality:")
    html = html.replace(
        "Continuation edge DEV/OOS:", f"Continuation edge {year}:"
    )
    html = html.replace(" / ${x.continuation_edge_oos.toFixed(2)}", "")
    html = html.replace("Reversal edge DEV/OOS:", f"Reversal edge {year}:")
    html = html.replace(" / ${x.reversal_edge_oos.toFixed(2)}", "")
    html = html.replace("<b>Selected OOS edge:", f"<b>Selected {year} edge:")
    html = html.replace("Class: ${x.robust_zone?'ROBUST':", "Class: ${x.robust_zone?'PARENT-CONFIRMED':")
    html = html.replace("Rows DEV/OOS:", f"Rows {year}:")
    html = html.replace("/${x.rows_oos}", "")
    return html


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--zones", type=Path, default=DEFAULT_ZONES)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "generated")
    args = parser.parse_args()

    zones = pd.read_csv(args.zones)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for year in (2023, 2024):
        output = args.output_dir / f"EURUSD_MARKET_MAP_TRADABILITY_{year}.html"
        output.write_text(annual_html(zones, year), encoding="utf-8")
        print(year, output)


if __name__ == "__main__":
    main()
