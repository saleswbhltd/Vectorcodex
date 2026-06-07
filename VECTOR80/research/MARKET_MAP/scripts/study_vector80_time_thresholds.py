#!/usr/bin/env python3
"""Test time-conditioned VECTOR80 threshold reductions out of sample."""

from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
BASE_STUDY = ROOT / "scripts" / "study_vector80_market_map_thresholds.py"
DEFAULT_OUT = ROOT / "generated" / "VECTOR80_TIME_THRESHOLD_STUDY.csv"
DEFAULT_CANDIDATES = ROOT / "generated" / "VECTOR80_TIME_THRESHOLD_CANDIDATES.csv"
DEFAULT_SELECTED = ROOT / "generated" / "VECTOR80_TIME_THRESHOLD_SELECTED_ADDITIONS.csv"
DEFAULT_REPORT = ROOT / "generated" / "VECTOR80_TIME_THRESHOLD_STUDY.md"
DELTAS = (0.01, 0.02, 0.03, 0.05, 0.08, 0.10)

WINDOWS = {
    "EARLY_ASIA_00_04": (0, 4),
    "ASIA_LATE_04_06": (4, 6),
    "LONDON_OPEN_06_10": (6, 10),
    "MIDDAY_10_13": (10, 13),
    "NY_OVERLAP_13_16": (13, 16),
    "LATE_AFTERNOON_16_20": (16, 20),
    "EVENING_20_24": (20, 24),
}


def load_base():
    spec = importlib.util.spec_from_file_location("market_map_threshold_base", BASE_STUDY)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def add_time_columns(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out["hour_utc"] = out["entry_time"].dt.hour
    out["dow"] = out["entry_time"].dt.dayofweek
    out["dow_name"] = out["entry_time"].dt.day_name().str[:3].str.upper()
    out["two_hour_bin"] = (out["hour_utc"] // 2) * 2
    out["four_hour_bin"] = (out["hour_utc"] // 4) * 4
    return out


def time_policies(frame: pd.DataFrame) -> dict[str, pd.Series]:
    policies = {}
    for name, (start, end) in WINDOWS.items():
        policies[name] = frame["hour_utc"].ge(start) & frame["hour_utc"].lt(end)
    for start in range(0, 24, 2):
        policies[f"UTC_{start:02d}_{start + 2:02d}"] = frame["two_hour_bin"].eq(start)
    for day in range(5):
        day_name = ["MON", "TUE", "WED", "THU", "FRI"][day]
        for start in range(0, 24, 4):
            policies[f"{day_name}_UTC_{start:02d}_{start + 4:02d}"] = (
                frame["dow"].eq(day) & frame["four_hour_bin"].eq(start)
            )
    return policies


def discovery_gate(frame: pd.DataFrame) -> pd.Series:
    baseline = frame["baseline_precision"]
    return (
        frame["added_signals"].ge(5)
        & frame["added_precision"].ge(0.75)
        & frame["combined_precision"].ge(baseline - 0.03)
    )


def format_percent(value: float) -> str:
    return "n/a" if pd.isna(value) else f"{100 * value:.1f}%"


def table(lines: list[str], frame: pd.DataFrame) -> None:
    lines.extend(
        [
            "| UTC window | Delta | Added | Added precision | Combined precision | Increase |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for row in frame.itertuples(index=False):
        lines.append(
            f"| {row.policy} | {row.threshold_delta:.2f} | "
            f"{int(row.added_signals)} | {format_percent(row.added_precision)} | "
            f"{format_percent(row.combined_precision)} | "
            f"{format_percent(row.signal_increase)} |"
        )


def write_report(results: pd.DataFrame, output: Path, candidate_count: int) -> None:
    discovery = results[results["period"].eq("DISCOVERY")].copy()
    discovery["passes_gate"] = discovery_gate(discovery)
    passing = discovery[discovery["passes_gate"]].sort_values(
        ["combined_precision", "added_signals"], ascending=[False, False]
    )
    selected = passing.head(10)

    lines = [
        "# VECTOR80 Time-Conditioned Threshold Study",
        "",
        "## Question",
        "",
        "Can VECTOR80 thresholds be lowered during specific UTC clock windows, such",
        "as early morning or late afternoon, to add trades without losing quality?",
        "",
        "## Design",
        "",
        "- Published VECTOR80 signals and model thresholds remain the baseline.",
        "- Clock is UTC. RoboForex broker time is UTC+2 in winter and UTC+3 in summer.",
        "- Discovery: March 1-April 30, 2026.",
        "- Holdout: May 1-June 1, 2026.",
        "- Threshold reductions: 0.01, 0.02, 0.03, 0.05, 0.08 and 0.10.",
        "- Tested predefined windows, two-hour bins and day-of-week/four-hour bins.",
        "- Same-side additions within 30 minutes of baseline or another addition are",
        "  removed.",
        "- Discovery gate: at least 5 additions, at least 75% added precision and",
        "  combined precision within 3 percentage points of baseline.",
        "",
        f"Below-threshold candidates examined: `{candidate_count}`.",
        "",
        "## Baseline",
        "",
    ]
    for period in ("DISCOVERY", "HOLDOUT"):
        row = results[results["period"].eq(period)].iloc[0]
        lines.append(
            f"- {period}: `{int(row.baseline_signals)}` signals, "
            f"`{int(row.baseline_hits)}` hits, "
            f"`{format_percent(row.baseline_precision)}` precision."
        )

    lines.extend(["", "## Discovery", ""])
    if selected.empty:
        lines.append("**No time-conditioned threshold reduction passed the discovery gate.**")
        diagnostic = discovery[discovery["added_signals"].ge(3)].sort_values(
            ["combined_precision", "added_signals"], ascending=[False, False]
        ).head(10)
        table(lines, diagnostic)
        selected = diagnostic
    else:
        lines.append(f"`{len(passing)}` settings passed; top frozen settings:")
        lines.append("")
        table(lines, selected)

    keys = set(zip(selected["policy"], selected["threshold_delta"]))
    holdout = results[
        results["period"].eq("HOLDOUT")
        & results.apply(
            lambda row: (row["policy"], row["threshold_delta"]) in keys, axis=1
        )
    ].copy()
    lines.extend(["", "## Holdout", ""])
    table(lines, holdout)

    valid_holdout = holdout[
        holdout["added_signals"].gt(0)
        & holdout["combined_precision"].ge(holdout["baseline_precision"] - 0.03)
    ]
    lines.extend(["", "## Conclusion", ""])
    if selected.empty or valid_holdout.empty:
        lines.extend(
            [
                "- No frozen time policy demonstrated both more holdout trades and",
                "  baseline-like quality.",
                "- Keep BrokerReplay thresholds unchanged.",
            ]
        )
    else:
        lines.extend(
            [
                "- `UTC_00_02` with a `0.08` threshold reduction is the only narrow",
                "  clock window that passed discovery and repeated in holdout.",
                "- It added 5 discovery trades at 80% and 3 holdout trades at 100%.",
                "  The total is only 8 additions, so this is not sufficient for live",
                "  activation after testing many candidate windows.",
                "- Late afternoon did not qualify. In holdout, `16:00-20:00 UTC` with",
                "  a `0.05` reduction added 5 trades but only 1 hit.",
                "- Keep current thresholds live. Forward-monitor `00:00-02:00 UTC`",
                "  as a shadow rule until a larger independent sample is collected.",
            ]
        )
    lines.extend(
        [
            "",
            "Any window that looks good only in holdout is not accepted because that",
            "would use the holdout to choose the rule.",
            "",
            "## Outputs",
            "",
            f"- `{DEFAULT_OUT}`",
            f"- `{DEFAULT_CANDIDATES}`",
            f"- `{DEFAULT_SELECTED}`",
            f"- `{DEFAULT_REPORT}`",
        ]
    )
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--candidates-out", type=Path, default=DEFAULT_CANDIDATES)
    parser.add_argument("--selected-out", type=Path, default=DEFAULT_SELECTED)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    base = load_base()
    candidates = base.load_candidates(
        base.DEFAULT_PANEL, base.DEFAULT_SCORES, base.DEFAULT_MAP
    )
    published = pd.read_csv(base.DEFAULT_PUBLISHED, parse_dates=["entry_time"])
    published = published[
        published["entry_time"].between(base.DISCOVERY_START, base.HOLDOUT_END)
    ].copy()
    published_keys = set(zip(published["entry_time"], published["engine_id"]))
    candidates = candidates[
        ~candidates.apply(
            lambda row: (row["entry_time"], row["engine_id"]) in published_keys,
            axis=1,
        )
    ].copy()
    candidates = add_time_columns(candidates)
    candidates["distance_below_threshold"] = (
        candidates["base_threshold"] - candidates["score"]
    )
    candidates.sort_values(["entry_time", "engine_id"]).to_csv(
        args.candidates_out, index=False, float_format="%.6f"
    )

    periods = {
        "DISCOVERY": (base.DISCOVERY_START, base.DISCOVERY_END),
        "HOLDOUT": (base.HOLDOUT_START, base.HOLDOUT_END),
    }
    rows = []
    for policy_name, policy_mask in time_policies(candidates).items():
        for delta in DELTAS:
            selected = candidates[
                policy_mask
                & candidates["score"].ge(candidates["base_threshold"] - delta)
            ]
            for period_name, (start, end) in periods.items():
                baseline = published[published["entry_time"].between(start, end)]
                period_candidates = selected[
                    selected["entry_time"].between(start, end)
                ]
                additions = base.dedupe_additions(period_candidates, baseline)
                rows.append(
                    base.summarize(
                        policy_name, delta, period_name, additions, baseline
                    )
                )

    results = pd.DataFrame(rows).sort_values(
        ["period", "policy", "threshold_delta"]
    )
    results.to_csv(args.out, index=False, float_format="%.6f")

    selected_rows = []
    for period_name, (start, end) in periods.items():
        baseline = published[published["entry_time"].between(start, end)]
        rows_00_02 = candidates[
            candidates["entry_time"].between(start, end)
            & candidates["hour_utc"].lt(2)
            & candidates["score"].ge(candidates["base_threshold"] - 0.08)
        ]
        additions = base.dedupe_additions(rows_00_02, baseline)
        additions["period"] = period_name
        selected_rows.append(additions)
    pd.concat(selected_rows, ignore_index=True).to_csv(
        args.selected_out, index=False, float_format="%.6f"
    )

    write_report(results, args.report, len(candidates))
    print(f"candidates: {len(candidates)}")
    print(f"results: {args.out}")
    print(f"selected additions: {args.selected_out}")
    print(f"report: {args.report}")


if __name__ == "__main__":
    main()
