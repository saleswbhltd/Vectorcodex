#!/usr/bin/env python3
"""Build parity-safe 2023/2024 tradability maps and measure zone drift."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

try:
    from scripts.study_tradability_zones import DAYS, rank_dev
    from scripts.validate_tradability_historical_holdout import (
        aggregate_holdout,
        prepare_adjusted_frame,
    )
except ModuleNotFoundError:
    from study_tradability_zones import DAYS, rank_dev
    from validate_tradability_historical_holdout import (
        aggregate_holdout,
        prepare_adjusted_frame,
    )


ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = Path(
    "/home/cmake/VectorShared/research/dukascopy/EURUSD/2023_2024/broker_adjusted"
)
DEFAULT_OUT = ROOT / "generated" / "MARKET_MAP_tradability_2023_2024_comparison.csv"
DEFAULT_REPORT = ROOT / "generated" / "MARKET_MAP_TRADABILITY_2023_2024_COMPARISON.md"
DEFAULT_HTML = ROOT / "generated" / "EURUSD_MARKET_MAP_TRADABILITY_2023_2024.html"


def classify_year(zones: pd.DataFrame, year: int) -> pd.DataFrame:
    out = rank_dev(zones).copy()
    out["year"] = year
    out["selected_edge"] = np.where(
        out["strategy_fit"].eq("CONTINUATION"),
        out["continuation_edge"],
        out["reversal_edge"],
    )
    out["selected_win_rate"] = np.where(
        out["strategy_fit"].eq("CONTINUATION"),
        out["continuation_win_rate"],
        out["reversal_win_rate"],
    )
    out["positive_zone"] = out["strategy_fit"].ne("AVOID") & out["selected_edge"].gt(0)
    return out


def add_year_parent_confirmation(zones: pd.DataFrame) -> pd.DataFrame:
    out = zones.copy()
    out["parent_30m_positive"] = False
    out["parent_30m_strategy"] = ""
    parents = out[out["resolution_min"].eq(30)]
    lookup = {
        (row.year, row.day, row.time): (
            bool(row.positive_zone),
            row.strategy_fit,
        )
        for row in parents.itertuples()
    }
    for index, row in out[out["resolution_min"].eq(15)].iterrows():
        hour, minute = map(int, row["time"].split(":"))
        parent_time = f"{hour:02d}:{(minute // 30) * 30:02d}"
        positive, strategy = lookup.get(
            (row["year"], row["day"], parent_time), (False, "")
        )
        out.at[index, "parent_30m_positive"] = positive
        out.at[index, "parent_30m_strategy"] = strategy
    out["parent_confirmed"] = (
        out["positive_zone"]
        & (
            out["resolution_min"].eq(30)
            | (
                out["parent_30m_positive"]
                & out["strategy_fit"].eq(out["parent_30m_strategy"])
            )
        )
    )
    return out


def minute_distance(left: int, right: int) -> int:
    distance = abs(left - right)
    return min(distance, 1440 - distance)


def nearby_persistence(
    source: pd.DataFrame, target: pd.DataFrame, tolerance: int = 30
) -> pd.DataFrame:
    rows = []
    target = target[target["parent_confirmed"]]
    for zone in source[source["parent_confirmed"]].itertuples():
        candidates = target[
            target["day"].eq(zone.day)
            & target["strategy_fit"].eq(zone.strategy_fit)
        ].copy()
        if candidates.empty:
            distance = np.nan
            target_time = ""
        else:
            candidates["distance_min"] = candidates["slot"].map(
                lambda slot: minute_distance(
                    int(zone.slot) * int(zone.resolution_min),
                    int(slot) * int(zone.resolution_min),
                )
            )
            best = candidates.sort_values(
                ["distance_min", "best_quality"], ascending=[True, False]
            ).iloc[0]
            distance = int(best["distance_min"])
            target_time = str(best["time"])
        rows.append(
            {
                "day": zone.day,
                "source_time": zone.time,
                "strategy": zone.strategy_fit,
                "source_edge": zone.selected_edge,
                "nearest_target_time": target_time,
                "distance_min": distance,
                "within_tolerance": bool(np.isfinite(distance) and distance <= tolerance),
            }
        )
    return pd.DataFrame(rows)


def compare_years(zones: pd.DataFrame) -> tuple[pd.DataFrame, dict, pd.DataFrame]:
    primary = zones[zones["resolution_min"].eq(15)]
    left = primary[primary["year"].eq(2023)]
    right = primary[primary["year"].eq(2024)]
    joined = left.merge(
        right,
        on=["dow_index", "slot", "day", "time", "resolution_min"],
        suffixes=("_2023", "_2024"),
    )
    joined["strategy_same"] = joined["strategy_fit_2023"].eq(
        joined["strategy_fit_2024"]
    )
    joined["edge_change"] = (
        joined["selected_edge_2024"] - joined["selected_edge_2023"]
    )
    joined["quality_change"] = (
        joined["best_quality_2024"] - joined["best_quality_2023"]
    )
    joined["liquidity_change"] = (
        joined["liquidity_score_2024"] - joined["liquidity_score_2023"]
    )
    joined["cleanliness_change"] = (
        joined["future_cleanliness_2024"] - joined["future_cleanliness_2023"]
    )
    exact = joined[
        joined["parent_confirmed_2023"] & joined["parent_confirmed_2024"]
    ]
    exact_same_strategy = exact[exact["strategy_same"]]
    nearby = nearby_persistence(left, right)
    quality_rho = float(
        spearmanr(joined["best_quality_2023"], joined["best_quality_2024"]).statistic
    )
    edge_rho = float(
        spearmanr(joined["selected_edge_2023"], joined["selected_edge_2024"]).statistic
    )
    metrics = {
        "zones": int(len(joined)),
        "positive_2023": int(left["positive_zone"].sum()),
        "positive_2024": int(right["positive_zone"].sum()),
        "parent_confirmed_2023": int(left["parent_confirmed"].sum()),
        "parent_confirmed_2024": int(right["parent_confirmed"].sum()),
        "exact_parent_confirmed_overlap": int(len(exact)),
        "exact_same_strategy_overlap": int(len(exact_same_strategy)),
        "parent_confirmed_jaccard": float(
            len(exact)
            / max(
                int(left["parent_confirmed"].sum())
                + int(right["parent_confirmed"].sum())
                - len(exact),
                1,
            )
        ),
        "exact_overlap_share_of_2023": float(
            len(exact) / max(int(left["parent_confirmed"].sum()), 1)
        ),
        "nearby_30m_share_of_2023": float(nearby["within_tolerance"].mean()),
        "strategy_agreement_all_cells": float(joined["strategy_same"].mean()),
        "quality_spearman": quality_rho,
        "selected_edge_spearman": edge_rho,
    }
    return joined, metrics, nearby


def markdown(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "No rows."
    columns = list(frame.columns)
    lines = [
        "| " + " | ".join(columns) + " |",
        "|" + "|".join("---" for _ in columns) + "|",
    ]
    for row in frame.itertuples(index=False, name=None):
        lines.append("| " + " | ".join(str(value) for value in row) + " |")
    return "\n".join(lines)


def write_report(
    zones: pd.DataFrame,
    comparison: pd.DataFrame,
    metrics: dict,
    nearby: pd.DataFrame,
    output: Path,
) -> None:
    exact = comparison[
        comparison["parent_confirmed_2023"]
        & comparison["parent_confirmed_2024"]
    ].copy()
    exact["mean_edge"] = (
        exact["selected_edge_2023"] + exact["selected_edge_2024"]
    ) / 2
    exact_table = exact.sort_values("mean_edge", ascending=False)[
        [
            "day",
            "time",
            "strategy_fit_2023",
            "selected_edge_2023",
            "selected_edge_2024",
            "best_quality_2023",
            "best_quality_2024",
        ]
    ].head(30).round(3)
    moved = nearby[
        nearby["within_tolerance"]
        & nearby["distance_min"].gt(0)
    ].sort_values(["distance_min", "day", "source_time"]).round(3)
    lines = [
        "# EURUSD Advanced Tradability Zones: 2023 vs 2024",
        "",
        "Both years are built independently with the parity-audited canonical",
        "steps 33, 34, 35 and 84, followed by the unchanged advanced tradability",
        "feature, outcome, ranking and 15/30-minute aggregation methods.",
        "",
        "## Important Definition",
        "",
        "`Parent-confirmed` means a positive 15-minute zone has a positive 30-minute",
        "parent with the same continuation/reversal archetype in that same year.",
        "It is not OOS robustness because each annual map ranks and evaluates itself.",
        "",
        "## Summary",
        "",
        f"- Positive 15-minute zones: `{metrics['positive_2023']}` in 2023 and "
        f"`{metrics['positive_2024']}` in 2024.",
        f"- Parent-confirmed zones: `{metrics['parent_confirmed_2023']}` in 2023 and "
        f"`{metrics['parent_confirmed_2024']}` in 2024.",
        f"- Exact parent-confirmed overlap: `{metrics['exact_parent_confirmed_overlap']}` "
        f"({metrics['exact_overlap_share_of_2023']:.1%} of the 2023 set).",
        f"- Exact overlap retaining the same strategy archetype: "
        f"`{metrics['exact_same_strategy_overlap']}/"
        f"{metrics['exact_parent_confirmed_overlap']}`.",
        f"- Parent-confirmed set Jaccard overlap: "
        f"`{metrics['parent_confirmed_jaccard']:.1%}`.",
        f"- 2023 parent-confirmed zones with a same-day/same-strategy 2024 zone within",
        f"  30 minutes: `{metrics['nearby_30m_share_of_2023']:.1%}`.",
        f"- Strategy-label agreement across all cells: "
        f"`{metrics['strategy_agreement_all_cells']:.1%}`.",
        f"- Quality-rank Spearman correlation: `{metrics['quality_spearman']:.3f}`.",
        f"- Selected-edge Spearman correlation: `{metrics['selected_edge_spearman']:.3f}`.",
        "",
        "## Exact Persistent Zones",
        "",
        markdown(exact_table),
        "",
        "## Nearby Time Shifts",
        "",
        markdown(moved.head(40)),
        "",
        "## Interpretation",
        "",
        "- Exact overlap measures timetable stability; nearby overlap detects gradual",
        "  movement that a fixed time-cell comparison would miss.",
        "- Exact cells that switch continuation/reversal remain active windows, but",
        "  their optimal strategy changed with the annual market regime.",
        "- A weak edge correlation with a stronger quality correlation would mean the",
        "  broad activity/liquidity structure persists while trade outcomes rotate.",
        "- Changes can reflect macro regime, daylight behavior, provider-domain",
        "  calibration stability and sampling noise, not only a permanent clock shift.",
        "- These maps are descriptive annual studies. A zone must still validate in a",
        "  later period before changing live thresholds.",
    ]
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def html_document(zones: pd.DataFrame, comparison: pd.DataFrame) -> str:
    primary = zones[zones["resolution_min"].eq(15)].copy()
    fields = [
        "year", "day", "time", "strategy_fit", "best_quality", "selected_edge",
        "selected_win_rate", "liquidity_score", "spread_atr",
        "future_cleanliness", "positive_zone", "parent_confirmed", "rows",
    ]
    data = json.dumps(primary[fields].to_dict(orient="records"), separators=(",", ":"))
    drift_fields = [
        "day", "time", "strategy_same", "edge_change", "quality_change",
        "parent_confirmed_2023", "parent_confirmed_2024",
    ]
    drift = json.dumps(
        comparison[drift_fields].to_dict(orient="records"), separators=(",", ":")
    )
    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
<title>EURUSD Tradability 2023 vs 2024</title><style>
body{{background:#0d1117;color:#c9d1d9;font:13px Segoe UI,sans-serif;padding:18px}}
h1{{font-size:19px}}button{{padding:7px 13px;margin:0 5px 10px 0;background:#161b22;color:#9ba7b4;border:1px solid #30363d;border-radius:5px}}
button.on{{background:#1f6feb;color:white}}table{{border-collapse:collapse;background:#161b22}}th{{font-size:9px;color:#6e7681;min-width:30px}}
td{{border:1px solid #0d1117;height:38px;min-width:30px;text-align:center;font-size:9px;font-weight:700}}
td.day{{min-width:90px;text-align:left;padding-left:6px}}.wrap{{overflow-x:auto}}.note{{padding:10px;background:#161b22;border:1px solid #30363d;margin:10px 0}}
#tip{{display:none;position:fixed;background:#1c2128;border:1px solid #484f58;padding:9px;z-index:5;line-height:1.55}}
</style></head><body><h1>EURUSD Advanced Tradability Zones: 2023 vs 2024</h1>
<div class="note">Same canonical tick, panel, calibration and tradability method for both years. Green = positive with matching positive 30-minute parent; amber = positive without parent confirmation; red = avoid or negative. Drift view shows quality change from 2023 to 2024.</div>
<button id="b2023" onclick="view='2023';draw()">2023</button><button id="b2024" onclick="view='2024';draw()">2024</button><button id="bdrift" onclick="view='drift';draw()">2024 − 2023</button>
<div class="wrap"><table id="t"></table></div><div id="tip"></div>
<script>const D={data},R={drift},DAYS={DAYS!r};let view='2023';const tip=document.getElementById('tip'),t=document.getElementById('t');
const by={{}},dr={{}};D.forEach(x=>by[x.year+'|'+x.day+'|'+x.time]=x);R.forEach(x=>dr[x.day+'|'+x.time]=x);
function color(x){{if(!x)return'#0d1117';if(view==='drift'){{let q=Math.max(-25,Math.min(25,x.quality_change));return q>=0?`rgb(25,${{80+Math.round(q*5)}},55)`:`rgb(${{90+Math.round(-q*5)}},35,45)`}}if(x.parent_confirmed)return'#238636';if(x.positive_zone)return'#8a6d1d';return'#702c36'}}
function draw(){{t.innerHTML='';document.querySelectorAll('button').forEach(b=>b.classList.remove('on'));document.getElementById('b'+view).classList.add('on');let h=t.insertRow();h.insertCell();for(let i=0;i<96;i++){{let c=h.insertCell();c.textContent=i%4===0?String(i/4).padStart(2,'0'):''}}DAYS.forEach(day=>{{let r=t.insertRow(),d=r.insertCell();d.className='day';d.textContent=day;for(let i=0;i<96;i++){{let tm=String(Math.floor(i/4)).padStart(2,'0')+':'+String((i%4)*15).padStart(2,'0'),x=view==='drift'?dr[day+'|'+tm]:by[view+'|'+day+'|'+tm],c=r.insertCell();c.style.background=color(x);c.textContent=!x?'':view==='drift'?(x.quality_change>=0?'+':'')+x.quality_change.toFixed(0):(x.strategy_fit==='CONTINUATION'?'C':x.strategy_fit==='REVERSAL'?'R':'—');c.onmouseenter=e=>{{if(!x)return;tip.innerHTML=view==='drift'?`<b>${{day}} ${{tm}} UTC</b><br>Quality change: ${{x.quality_change.toFixed(1)}}<br>Edge change: ${{x.edge_change.toFixed(2)}} pips<br>Same strategy: ${{x.strategy_same}}<br>Parent confirmed 2023/2024: ${{x.parent_confirmed_2023}} / ${{x.parent_confirmed_2024}}`:`<b>${{view}} ${{day}} ${{tm}} UTC · ${{x.strategy_fit}}</b><br>Quality ${{x.best_quality.toFixed(1)}} · edge ${{x.selected_edge.toFixed(2)}} pips<br>Win rate ${{(100*x.selected_win_rate).toFixed(1)}}% · rows ${{x.rows}}<br>Liquidity ${{x.liquidity_score.toFixed(1)}} · spread/ATR ${{x.spread_atr.toFixed(3)}}<br>Cleanliness ${{x.future_cleanliness.toFixed(3)}}<br>Parent confirmed: ${{x.parent_confirmed}}`;tip.style.display='block';tip.style.left=e.clientX+10+'px';tip.style.top=e.clientY-5+'px'}};c.onmouseleave=()=>tip.style.display='none'}}}})}}draw();
</script></body></html>"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, default=ARCHIVE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--html", type=Path, default=DEFAULT_HTML)
    args = parser.parse_args()

    yearly = []
    for year in (2023, 2024):
        panel = args.archive / f"EURUSD_M5_broker_adjusted_{year}.csv.gz"
        frame = prepare_adjusted_frame(panel)
        for resolution in (15, 30):
            zones = aggregate_holdout(
                frame, f"{year}-01-01", f"{year + 1}-01-01", resolution
            )
            yearly.append(classify_year(zones, year))
    zones = add_year_parent_confirmation(pd.concat(yearly, ignore_index=True))
    comparison, metrics, nearby = compare_years(zones)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    zones.to_csv(
        args.out.with_name("MARKET_MAP_tradability_yearly_zones.csv"),
        index=False,
        float_format="%.6f",
    )
    comparison.to_csv(args.out, index=False, float_format="%.6f")
    nearby.to_csv(
        args.out.with_name("MARKET_MAP_tradability_nearby_drift.csv"),
        index=False,
        float_format="%.6f",
    )
    write_report(zones, comparison, metrics, nearby, args.report)
    args.html.write_text(html_document(zones, comparison), encoding="utf-8")
    print(json.dumps(metrics, indent=2))
    print("report:", args.report)
    print("html:", args.html)


if __name__ == "__main__":
    main()
