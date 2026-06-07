#!/usr/bin/env python3
"""Scan every UTC 15-minute slot for VECTOR80 threshold reductions."""

from __future__ import annotations

import argparse
import html
import importlib.util
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
BASE_SCRIPT = ROOT / "scripts" / "study_vector80_market_map_thresholds.py"
DEFAULT_CANDIDATES = ROOT / "generated" / "VECTOR80_TIME_THRESHOLD_CANDIDATES.csv"
DEFAULT_OUT = ROOT / "generated" / "VECTOR80_15M_THRESHOLD_ZONES.csv"
DEFAULT_SUMMARY = ROOT / "generated" / "VECTOR80_15M_THRESHOLD_ZONE_SUMMARY.csv"
DEFAULT_REPORT = ROOT / "generated" / "VECTOR80_15M_THRESHOLD_ZONES.md"
DEFAULT_HTML = ROOT / "generated" / "EURUSD_VECTOR80_15M_THRESHOLD_ZONES.html"
DELTAS = (0.01, 0.02, 0.03, 0.05, 0.08, 0.10)


def load_base():
    spec = importlib.util.spec_from_file_location("threshold_base", BASE_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def slot_index(timestamp: pd.Timestamp) -> int:
    return timestamp.hour * 4 + timestamp.minute // 15


def slot_name(slot: int) -> str:
    hour, quarter = divmod(slot, 4)
    return f"{hour:02d}:{quarter * 15:02d}"


def outcome_status(hits: int, count: int) -> str:
    if count == 0:
        return "NO_TRADES"
    rate = hits / count
    if rate > 0.5:
        return "WINNING"
    if rate == 0.5:
        return "BREAKEVEN"
    return "LOSING"


def repeatability_status(row: pd.Series) -> str:
    discovery_count = int(row["discovery_added"])
    holdout_count = int(row["holdout_added"])
    discovery_rate = row["discovery_precision"]
    holdout_rate = row["holdout_precision"]
    discovery_positive = discovery_count > 0 and discovery_rate > 0.5
    holdout_positive = holdout_count > 0 and holdout_rate > 0.5
    discovery_bad = discovery_count > 0 and discovery_rate <= 0.5
    holdout_bad = holdout_count > 0 and holdout_rate <= 0.5

    if discovery_positive and holdout_positive:
        return "REPEATED_POSITIVE"
    if discovery_bad and holdout_bad:
        return "REPEATED_WEAK"
    if discovery_positive and holdout_bad:
        return "FAILED_HOLDOUT"
    if discovery_bad and holdout_positive:
        return "HOLDOUT_ONLY_POSITIVE"
    if discovery_positive:
        return "DISCOVERY_ONLY_POSITIVE"
    if holdout_positive:
        return "HOLDOUT_ONLY_POSITIVE"
    if discovery_count + holdout_count > 0:
        return "WEAK_OR_MIXED"
    return "NO_DATA"


def scan(
    candidates: pd.DataFrame,
    published: pd.DataFrame,
    base,
) -> pd.DataFrame:
    candidates = candidates.copy()
    candidates["slot"] = candidates["entry_time"].map(slot_index)
    periods = {
        "DISCOVERY": (base.DISCOVERY_START, base.DISCOVERY_END),
        "HOLDOUT": (base.HOLDOUT_START, base.HOLDOUT_END),
    }
    rows = []
    for delta in DELTAS:
        threshold_candidates = candidates[
            candidates["score"].ge(candidates["base_threshold"] - delta)
        ]
        for slot in range(96):
            slot_candidates = threshold_candidates[
                threshold_candidates["slot"].eq(slot)
            ]
            for period, (start, end) in periods.items():
                baseline = published[published["entry_time"].between(start, end)]
                additions = base.dedupe_additions(
                    slot_candidates[
                        slot_candidates["entry_time"].between(start, end)
                    ],
                    baseline,
                )
                count = len(additions)
                hits = int(additions["is_hit"].sum()) if count else 0
                rows.append(
                    {
                        "threshold_delta": delta,
                        "slot": slot,
                        "utc_time": slot_name(slot),
                        "period": period,
                        "added_trades": count,
                        "hits": hits,
                        "losses": count - hits,
                        "precision": hits / count if count else float("nan"),
                        "status": outcome_status(hits, count),
                    }
                )
    return pd.DataFrame(rows)


def make_summary(results: pd.DataFrame) -> pd.DataFrame:
    discovery = results[results["period"].eq("DISCOVERY")].copy()
    holdout = results[results["period"].eq("HOLDOUT")].copy()
    discovery = discovery.rename(
        columns={
            "added_trades": "discovery_added",
            "hits": "discovery_hits",
            "losses": "discovery_losses",
            "precision": "discovery_precision",
            "status": "discovery_status",
        }
    )
    holdout = holdout.rename(
        columns={
            "added_trades": "holdout_added",
            "hits": "holdout_hits",
            "losses": "holdout_losses",
            "precision": "holdout_precision",
            "status": "holdout_status",
        }
    )
    keep = ["threshold_delta", "slot", "utc_time"]
    summary = discovery[
        keep
        + [
            "discovery_added",
            "discovery_hits",
            "discovery_losses",
            "discovery_precision",
            "discovery_status",
        ]
    ].merge(
        holdout[
            keep
            + [
                "holdout_added",
                "holdout_hits",
                "holdout_losses",
                "holdout_precision",
                "holdout_status",
            ]
        ],
        on=keep,
        validate="one_to_one",
    )
    summary["total_added"] = summary["discovery_added"] + summary["holdout_added"]
    summary["total_hits"] = summary["discovery_hits"] + summary["holdout_hits"]
    summary["total_precision"] = (
        summary["total_hits"] / summary["total_added"].replace(0, pd.NA)
    )
    summary["repeatability"] = summary.apply(repeatability_status, axis=1)
    return summary


def fmt_rate(value: float) -> str:
    return "-" if pd.isna(value) else f"{100 * value:.0f}%"


def render_html(summary: pd.DataFrame, output: Path) -> None:
    colors = {
        "REPEATED_POSITIVE": "#137333",
        "DISCOVERY_ONLY_POSITIVE": "#b06000",
        "HOLDOUT_ONLY_POSITIVE": "#6f42c1",
        "FAILED_HOLDOUT": "#c5221f",
        "REPEATED_WEAK": "#8b0000",
        "WEAK_OR_MIXED": "#666666",
        "NO_DATA": "#dddddd",
    }
    sections = []
    for delta in DELTAS:
        current = summary[summary["threshold_delta"].eq(delta)].set_index("slot")
        rows = []
        for hour in range(24):
            cells = [f"<th>{hour:02d}:00</th>"]
            for quarter in range(4):
                row = current.loc[hour * 4 + quarter]
                status = str(row["repeatability"])
                color = colors[status]
                text = (
                    f"<b>{row['utc_time']}</b><br>"
                    f"D {int(row['discovery_hits'])}/{int(row['discovery_added'])} "
                    f"({fmt_rate(row['discovery_precision'])})<br>"
                    f"H {int(row['holdout_hits'])}/{int(row['holdout_added'])} "
                    f"({fmt_rate(row['holdout_precision'])})"
                )
                cells.append(
                    f"<td style='background:{color}' title='{html.escape(status)}'>{text}</td>"
                )
            rows.append("<tr>" + "".join(cells) + "</tr>")
        sections.append(
            f"<section><h2>Threshold reduction: {delta:.2f}</h2>"
            "<table><thead><tr><th>Hour</th><th>:00</th><th>:15</th>"
            "<th>:30</th><th>:45</th></tr></thead><tbody>"
            + "".join(rows)
            + "</tbody></table></section>"
        )

    document = f"""<!doctype html>
<html><head><meta charset="utf-8">
<title>VECTOR80 15-Minute Threshold Zones</title>
<style>
body{{font-family:Arial,sans-serif;margin:24px;background:#f7f7f7;color:#222}}
section{{background:white;padding:16px;margin:18px 0;box-shadow:0 1px 5px #bbb}}
table{{border-collapse:collapse;width:100%;table-layout:fixed}}
th,td{{border:1px solid #aaa;padding:7px;text-align:center;font-size:12px}}
td{{color:white;height:50px}} th{{background:#eee}}
.legend span{{display:inline-block;padding:7px 10px;margin:3px;color:white}}
</style></head><body>
<h1>EURUSD VECTOR80 15-Minute Threshold-Zone Scan</h1>
<p>UTC slots. D = March-April discovery. H = May 1-June 1 holdout.
Values are hits / added trades. Empty slots are gray. One-trade cells are
descriptive evidence, not validated zones.</p>
<div class="legend">
<span style="background:#137333">Repeated positive</span>
<span style="background:#b06000">Discovery only</span>
<span style="background:#6f42c1">Holdout only</span>
<span style="background:#c5221f">Failed holdout</span>
<span style="background:#8b0000">Repeated weak</span>
<span style="background:#666">Weak/mixed</span>
</div>
{''.join(sections)}
</body></html>"""
    output.write_text(document, encoding="utf-8")


def write_report(summary: pd.DataFrame, output: Path) -> None:
    repeated = summary[summary["repeatability"].eq("REPEATED_POSITIVE")].copy()
    repeated = repeated.sort_values(
        ["total_added", "total_precision"], ascending=[False, False]
    )
    failed = summary[summary["repeatability"].eq("FAILED_HOLDOUT")].copy()
    failed = failed.sort_values(
        ["discovery_added", "holdout_added"], ascending=False
    )
    lines = [
        "# VECTOR80 15-Minute Threshold-Zone Study",
        "",
        "Every one of the 96 UTC quarter-hour slots was tested at threshold",
        "reductions of 0.01, 0.02, 0.03, 0.05, 0.08 and 0.10.",
        "",
        "March-April 2026 is discovery. May 1-June 1, 2026 is untouched holdout.",
        "A cell is descriptive unless it has trades in both periods. Testing 576",
        "slot/delta combinations creates substantial multiple-testing risk.",
        "",
        "## Repeated Positive Cells",
        "",
        "| UTC slot | Delta | Discovery | Holdout | Total |",
        "|---|---:|---:|---:|---:|",
    ]
    if repeated.empty:
        lines.append("| None | - | - | - | - |")
    else:
        for row in repeated.head(30).itertuples(index=False):
            lines.append(
                f"| {row.utc_time} | {row.threshold_delta:.2f} | "
                f"{int(row.discovery_hits)}/{int(row.discovery_added)} | "
                f"{int(row.holdout_hits)}/{int(row.holdout_added)} | "
                f"{int(row.total_hits)}/{int(row.total_added)} |"
            )
    lines.extend(
        [
            "",
            "## Discovery Winners That Failed Holdout",
            "",
            "| UTC slot | Delta | Discovery | Holdout |",
            "|---|---:|---:|---:|",
        ]
    )
    if failed.empty:
        lines.append("| None | - | - | - |")
    else:
        for row in failed.head(20).itertuples(index=False):
            lines.append(
                f"| {row.utc_time} | {row.threshold_delta:.2f} | "
                f"{int(row.discovery_hits)}/{int(row.discovery_added)} | "
                f"{int(row.holdout_hits)}/{int(row.holdout_added)} |"
            )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- The CSV and HTML show every zone, including no-trade zones.",
            "- A winning cell means more than half of its added candidates hit the",
            "  existing VECTOR80 target definition; it does not prove future edge.",
            "- Prefer cells positive in both discovery and holdout, with several",
            "  independent trades. Do not enable isolated 1/1 cells.",
            "- The exact 15-minute scan is a diagnostic map. Neighboring-slot and",
            "  forward accumulation are required before changing the EA.",
            "",
            "## Outputs",
            "",
            f"- `{DEFAULT_OUT}`",
            f"- `{DEFAULT_SUMMARY}`",
            f"- `{DEFAULT_HTML}`",
            f"- `{DEFAULT_REPORT}`",
        ]
    )
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--html", type=Path, default=DEFAULT_HTML)
    args = parser.parse_args()

    base = load_base()
    candidates = pd.read_csv(args.candidates, parse_dates=["entry_time"])
    published = pd.read_csv(base.DEFAULT_PUBLISHED, parse_dates=["entry_time"])
    published = published[
        published["entry_time"].between(base.DISCOVERY_START, base.HOLDOUT_END)
    ]
    results = scan(candidates, published, base)
    summary = make_summary(results)
    results.to_csv(args.out, index=False, float_format="%.6f")
    summary.to_csv(args.summary, index=False, float_format="%.6f")
    render_html(summary, args.html)
    write_report(summary, args.report)
    print(f"raw zones: {args.out}")
    print(f"summary: {args.summary}")
    print(f"html: {args.html}")
    print(f"report: {args.report}")


if __name__ == "__main__":
    main()
