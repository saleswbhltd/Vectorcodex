#!/usr/bin/env python3
"""Test MARKET_MAP-conditioned VECTOR80 threshold reductions out of sample."""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
RESEARCH = Path("/home/cmake/VectorShared/research")
DEFAULT_PANEL = RESEARCH / "EURUSD_M5_FULL_PANEL.csv.gz"
DEFAULT_PUBLISHED = RESEARCH / "zzlines_code_ready_sell_expanded_oos_signals.csv"
DEFAULT_SCORES = ROOT / "generated" / "VECTOR80_model_scores_full_oos_diagnostics.csv"
DEFAULT_MAP = ROOT / "generated" / "MARKET_MAP_regime_predictions.csv.gz"
DEFAULT_OUT = ROOT / "generated" / "VECTOR80_MARKET_MAP_THRESHOLD_STUDY.csv"
DEFAULT_CANDIDATES = ROOT / "generated" / "VECTOR80_MARKET_MAP_THRESHOLD_CANDIDATES.csv"
DEFAULT_REPORT = ROOT / "generated" / "VECTOR80_MARKET_MAP_THRESHOLD_STUDY.md"

DISCOVERY_START = pd.Timestamp("2026-03-01")
DISCOVERY_END = pd.Timestamp("2026-04-30 23:55:00")
HOLDOUT_START = pd.Timestamp("2026-05-01")
HOLDOUT_END = pd.Timestamp("2026-06-01 23:55:00")
DELTAS = (0.01, 0.02, 0.03, 0.05, 0.08, 0.10)


def wilson(hits: int, count: int, z: float = 1.96) -> tuple[float, float]:
    if count <= 0:
        return 0.0, 1.0
    p = hits / count
    denominator = 1.0 + z * z / count
    center = (p + z * z / (2.0 * count)) / denominator
    margin = z * math.sqrt(p * (1.0 - p) / count + z * z / (4.0 * count * count))
    margin /= denominator
    return max(0.0, center - margin), min(1.0, center + margin)


def market_policies(frame: pd.DataFrame) -> dict[str, pd.Series]:
    opposing = frame["relation"].eq("OPPOSING")
    expansion = frame["volatility_actual"].eq("EXPANSION")
    trend = frame["structure_actual"].eq("TREND")
    chop = frame["structure_actual"].eq("CHOP")
    stretched = frame["current_net_atr"].abs().ge(1.25)
    efficient = frame["current_efficiency"].ge(0.40)
    strong = frame["current_net_atr"].abs().ge(2.50) & frame["current_efficiency"].ge(0.55)
    return {
        "ALL_STATES": pd.Series(True, index=frame.index),
        "OPPOSING_EXPANSION": opposing & expansion,
        "OPPOSING_TREND_EXPANSION": opposing & trend & expansion,
        "OPPOSING_CHOP_EXPANSION": opposing & chop & expansion,
        "OPPOSING_EXPANSION_STRETCHED": opposing & expansion & stretched,
        "OPPOSING_EXPANSION_EFFICIENT": opposing & expansion & efficient,
        "OPPOSING_STRONG_TREND": opposing & trend & strong,
    }


def dedupe_additions(
    additions: pd.DataFrame,
    published: pd.DataFrame,
    cooldown_minutes: int = 30,
) -> pd.DataFrame:
    if additions.empty:
        return additions.copy()
    rows = []
    for side, group in additions.groupby("side", sort=False):
        blocked = sorted(
            published.loc[published["side"].eq(side), "entry_time"].tolist()
        )
        kept_times: list[pd.Timestamp] = []
        ordered = group.sort_values(["entry_time", "score"], ascending=[True, False])
        for timestamp, same_time in ordered.groupby("entry_time", sort=True):
            candidate = same_time.sort_values("score", ascending=False).iloc[0]
            nearby_published = any(
                abs((timestamp - other).total_seconds()) < cooldown_minutes * 60
                for other in blocked
            )
            nearby_added = any(
                abs((timestamp - other).total_seconds()) < cooldown_minutes * 60
                for other in kept_times
            )
            if nearby_published or nearby_added:
                continue
            rows.append(candidate)
            kept_times.append(timestamp)
    if not rows:
        return additions.iloc[0:0].copy()
    return pd.DataFrame(rows).sort_values("entry_time").reset_index(drop=True)


def summarize(
    policy: str,
    delta: float,
    period: str,
    additions: pd.DataFrame,
    baseline: pd.DataFrame,
) -> dict:
    added_count = len(additions)
    added_hits = int(additions["is_hit"].sum()) if added_count else 0
    base_count = len(baseline)
    base_hits = int(baseline["is_hit"].sum()) if base_count else 0
    combined_count = base_count + added_count
    combined_hits = base_hits + added_hits
    lower, upper = wilson(added_hits, added_count)
    return {
        "policy": policy,
        "threshold_delta": delta,
        "period": period,
        "baseline_signals": base_count,
        "baseline_hits": base_hits,
        "baseline_precision": base_hits / base_count if base_count else np.nan,
        "added_signals": added_count,
        "added_hits": added_hits,
        "added_precision": added_hits / added_count if added_count else np.nan,
        "added_wilson_low": lower,
        "added_wilson_high": upper,
        "combined_signals": combined_count,
        "combined_hits": combined_hits,
        "combined_precision": combined_hits / combined_count if combined_count else np.nan,
        "signal_increase": added_count / base_count if base_count else np.nan,
    }


def load_candidates(
    panel_path: Path,
    score_path: Path,
    map_path: Path,
) -> pd.DataFrame:
    sys.path.insert(0, str(ROOT / "scripts"))
    from refresh_vector80_scores import (  # pylint: disable=import-outside-toplevel
        ENGINES,
        build_training_data,
        target_for_engine,
    )

    step64, _, _, _, _, catalog, rules = build_training_data()
    panel = pd.read_csv(panel_path, index_col=0, parse_dates=True).loc[
        DISCOVERY_START:HOLDOUT_END
    ]
    scores = pd.read_csv(score_path, parse_dates=["bar_time"])
    market_map = pd.read_csv(map_path, parse_dates=["datetime"]).set_index("datetime")
    map_columns = [
        "direction_actual",
        "structure_actual",
        "volatility_actual",
        "regime_actual",
        "current_net_atr",
        "current_efficiency",
        "current_range_atr",
        "current_range_expansion",
    ]

    rows = []
    for engine in ENGINES:
        stage1 = step64.stage1_mask(panel, rules, [engine.label])
        target = target_for_engine(panel, catalog, engine)
        engine_scores = (
            scores[scores["engine_id"].eq(engine.engine_id)]
            .set_index("bar_time")
            .reindex(panel.index)
        )
        score = engine_scores["score"].to_numpy(float)
        eligible = (
            stage1
            & np.isfinite(score)
            & (score < engine.threshold)
            & (score >= engine.threshold - max(DELTAS))
        )
        rows.append(
            pd.DataFrame(
                {
                    "entry_time": panel.index[eligible],
                    "engine_id": engine.engine_id,
                    "side": engine.side,
                    "score": score[eligible],
                    "base_threshold": engine.threshold,
                    "is_hit": target[eligible].astype(bool),
                }
            )
        )

    candidates = pd.concat(rows, ignore_index=True)
    candidates = candidates.merge(
        market_map[map_columns],
        left_on="entry_time",
        right_index=True,
        how="inner",
        validate="many_to_one",
    )
    candidates["relation"] = "OPPOSING"
    candidates.loc[candidates["direction_actual"].eq("NEUTRAL"), "relation"] = "NEUTRAL"
    aligned = (
        candidates["side"].eq("BUY") & candidates["direction_actual"].eq("BULL")
    ) | (
        candidates["side"].eq("SELL") & candidates["direction_actual"].eq("BEAR")
    )
    candidates.loc[aligned, "relation"] = "ALIGNED"
    return candidates


def period_mask(frame: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.Series:
    return frame["entry_time"].between(start, end)


def format_percent(value: float) -> str:
    return "n/a" if pd.isna(value) else f"{100.0 * value:.1f}%"


def write_report(results: pd.DataFrame, output: Path, candidate_count: int) -> None:
    discovery = results[results["period"].eq("DISCOVERY")].copy()
    baseline_precision = float(discovery["baseline_precision"].iloc[0])
    discovery["strict_pass"] = (
        discovery["added_signals"].ge(4)
        & discovery["added_precision"].ge(0.75)
        & discovery["combined_precision"].ge(baseline_precision - 0.03)
    )
    passing = discovery[discovery["strict_pass"]].sort_values(
        ["combined_precision", "added_signals"], ascending=[False, False]
    )

    lines = [
        "# VECTOR80 + MARKET_MAP Adaptive Threshold Study",
        "",
        "## Question",
        "",
        "Can MARKET_MAP identify conditions where VECTOR80 model thresholds can be",
        "lowered to add trades without materially reducing signal quality?",
        "",
        "## Design",
        "",
        "- VECTOR80 models, engine groups, stops, targets and published 42-signal",
        "  baseline are frozen.",
        "- MARKET_MAP uses only trailing completed-bar direction, structure and",
        "  volatility state. No future MARKET_MAP labels are used.",
        "- Policy discovery: March 1-April 30, 2026.",
        "- Untouched policy holdout: May 1-June 1, 2026.",
        "- Tested threshold reductions: 0.01, 0.02, 0.03, 0.05, 0.08 and 0.10.",
        "- Added candidates are blocked within 30 minutes of a published same-side",
        "  signal and deduplicated with the same 30-minute same-side interval.",
        "- Discovery acceptance requires at least 4 added signals, at least 75%",
        "  added precision and combined precision no more than 3 percentage points",
        "  below the frozen baseline.",
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

    lines.extend(["", "## Discovery Result", ""])
    if passing.empty:
        lines.append(
            "**No MARKET_MAP threshold-lowering policy passed the discovery gate.**"
        )
        candidates = discovery[discovery["added_signals"].ge(1)].sort_values(
            ["combined_precision", "added_signals"], ascending=[False, False]
        ).head(8)
    else:
        lines.append(
            f"`{len(passing)}` policy settings passed discovery. Their holdout "
            "results are shown below."
        )
        candidates = passing.head(8)

    lines.extend(
        [
            "",
            "| Policy | Delta | Added | Added precision | Combined precision | Increase |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for row in candidates.itertuples(index=False):
        lines.append(
            f"| {row.policy} | {row.threshold_delta:.2f} | {int(row.added_signals)} | "
            f"{format_percent(row.added_precision)} | "
            f"{format_percent(row.combined_precision)} | "
            f"{format_percent(row.signal_increase)} |"
        )

    lines.extend(["", "## Holdout", ""])
    selected_keys = set(zip(candidates["policy"], candidates["threshold_delta"]))
    holdout = results[
        results.apply(
            lambda row: (row["policy"], row["threshold_delta"]) in selected_keys,
            axis=1,
        )
        & results["period"].eq("HOLDOUT")
    ]
    lines.extend(
        [
            "| Policy | Delta | Added | Added precision | Combined precision | Increase |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for row in holdout.itertuples(index=False):
        lines.append(
            f"| {row.policy} | {row.threshold_delta:.2f} | {int(row.added_signals)} | "
            f"{format_percent(row.added_precision)} | "
            f"{format_percent(row.combined_precision)} | "
            f"{format_percent(row.signal_increase)} |"
        )

    lines.extend(["", "## Conclusion", ""])
    if passing.empty:
        lines.extend(
            [
                "- No policy was eligible for holdout deployment.",
                "- Keep all VECTOR80 thresholds unchanged.",
            ]
        )
    else:
        passing_holdout = holdout[
            holdout["added_signals"].gt(0)
            & holdout["combined_precision"].ge(
                holdout["baseline_precision"] - 0.03
            )
        ]
        if passing_holdout.empty:
            lines.extend(
                [
                    "- The only discovery-qualified policy added no holdout trades.",
                    "- It failed the objective of increasing trade count on unseen data.",
                    "  Keep all VECTOR80 thresholds unchanged.",
                    "- `OPPOSING_CHOP_EXPANSION` remains a forward-monitoring hypothesis,",
                    "  not an EA rule.",
                ]
            )
        else:
            lines.extend(
                [
                    "- At least one frozen policy added holdout trades within the",
                    "  non-inferiority margin. A larger forward sample is still required",
                    "  because the confidence intervals are wide.",
                ]
            )
    lines.extend(
        [
            "",
            "Larger deltas that look favorable only after inspecting holdout are",
            "reported in the CSV but are not accepted. Selecting them would leak the",
            "holdout into policy design.",
        ]
    )

    lines.extend(
        [
            "",
            "## Decision Rule",
            "",
            "Do not modify BrokerReplay unless a frozen policy adds trades on holdout",
            "while maintaining the agreed non-inferiority margin. Small samples must be",
            "treated as inconclusive even when observed precision is high.",
            "",
            "## Outputs",
            "",
            f"- `{DEFAULT_OUT}`",
            f"- `{DEFAULT_CANDIDATES}`",
            f"- `{DEFAULT_REPORT}`",
        ]
    )
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--panel", type=Path, default=DEFAULT_PANEL)
    parser.add_argument("--published", type=Path, default=DEFAULT_PUBLISHED)
    parser.add_argument("--scores", type=Path, default=DEFAULT_SCORES)
    parser.add_argument("--market-map", type=Path, default=DEFAULT_MAP)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--candidates-out", type=Path, default=DEFAULT_CANDIDATES)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    candidates = load_candidates(args.panel, args.scores, args.market_map)
    published = pd.read_csv(args.published, parse_dates=["entry_time"])
    published = published[
        published["entry_time"].between(DISCOVERY_START, HOLDOUT_END)
    ].copy()

    # The published validated entries stay fixed; only new rows are evaluated.
    published_keys = set(zip(published["entry_time"], published["engine_id"]))
    candidates = candidates[
        ~candidates.apply(
            lambda row: (row["entry_time"], row["engine_id"]) in published_keys,
            axis=1,
        )
    ].copy()
    candidates["distance_below_threshold"] = (
        candidates["base_threshold"] - candidates["score"]
    )
    args.candidates_out.parent.mkdir(parents=True, exist_ok=True)
    candidates.sort_values(["entry_time", "engine_id"]).to_csv(
        args.candidates_out, index=False, float_format="%.6f"
    )

    periods = {
        "DISCOVERY": (DISCOVERY_START, DISCOVERY_END),
        "HOLDOUT": (HOLDOUT_START, HOLDOUT_END),
    }
    rows = []
    policies = market_policies(candidates)
    for policy_name, policy_mask in policies.items():
        for delta in DELTAS:
            threshold_mask = candidates["score"].ge(
                candidates["base_threshold"] - delta
            )
            selected = candidates[policy_mask & threshold_mask].copy()
            for period_name, (start, end) in periods.items():
                baseline = published[
                    published["entry_time"].between(start, end)
                ].copy()
                period_candidates = selected[
                    selected["entry_time"].between(start, end)
                ].copy()
                additions = dedupe_additions(period_candidates, baseline)
                rows.append(
                    summarize(policy_name, delta, period_name, additions, baseline)
                )

    result = pd.DataFrame(rows).sort_values(
        ["period", "policy", "threshold_delta"]
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(args.out, index=False, float_format="%.6f")
    write_report(result, args.report, len(candidates))
    print(f"candidates: {len(candidates)}")
    print(f"results: {args.out}")
    print(f"candidate audit: {args.candidates_out}")
    print(f"report: {args.report}")


if __name__ == "__main__":
    main()
