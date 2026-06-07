#!/usr/bin/env python3
"""Build self-contained historical MARKET_MAP day/time heatmaps."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

try:
    from scripts.study_market_regimes import causalize_panel, current_path, label_axes
except ModuleNotFoundError:
    from study_market_regimes import causalize_panel, current_path, label_axes


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PANEL = Path("/home/cmake/VectorShared/research/EURUSD_M5_CALIBRATED_PANEL.csv.gz")
DEFAULT_HTML = ROOT / "generated" / "EURUSD_MARKET_MAP_HEATMAPS.html"
DEFAULT_CSV = ROOT / "generated" / "MARKET_MAP_heatmap_zones.csv"
DEFAULT_REPORT = ROOT / "generated" / "MARKET_MAP_HEATMAP_REPORT.md"
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]


def percentile(values: pd.Series) -> pd.Series:
    return values.rank(pct=True, method="average").fillna(0.5)


def build_resolution(frame: pd.DataFrame, minutes: int) -> tuple[dict, pd.DataFrame]:
    work = frame.copy()
    work["dow_index"] = work.index.dayofweek
    work["slot"] = (work.index.hour * 60 + work.index.minute) // minutes
    work["body_points"] = (work["close"] - work["open"]) / 0.00001
    work["range_points"] = (work["high"] - work["low"]) / 0.00001
    work["is_bull"] = work["current_direction_label"].eq("BULL")
    work["is_bear"] = work["current_direction_label"].eq("BEAR")
    work["is_neutral"] = work["current_direction_label"].eq("NEUTRAL")
    work["is_trend"] = work["current_structure_label"].eq("TREND")
    work["is_chop"] = work["current_structure_label"].eq("CHOP")
    work["is_range"] = work["current_structure_label"].eq("RANGE")
    work["is_expansion"] = work["current_volatility_label"].eq("EXPANSION")
    work["is_compression"] = work["current_volatility_label"].eq("COMPRESSION")
    work["is_normal_vol"] = work["current_volatility_label"].eq("NORMAL")
    work["is_strong"] = work["current_regime_label"].isin(
        ["STRONG_BULL_TREND", "STRONG_BEAR_TREND"]
    )
    work["strength_raw"] = (
        (work["current_net_atr"].abs() / 2.5).clip(upper=1.0)
        * (work["current_efficiency"] / 0.55).clip(upper=1.0)
    ) * 100.0

    grouped = work.groupby(["dow_index", "slot"], observed=True)
    zones = grouped.agg(
        count=("close", "size"),
        mean_body_points=("body_points", "mean"),
        mean_range_points=("range_points", "mean"),
        bull_share=("is_bull", "mean"),
        bear_share=("is_bear", "mean"),
        neutral_share=("is_neutral", "mean"),
        trend_share=("is_trend", "mean"),
        chop_share=("is_chop", "mean"),
        range_share=("is_range", "mean"),
        expansion_share=("is_expansion", "mean"),
        compression_share=("is_compression", "mean"),
        normal_vol_share=("is_normal_vol", "mean"),
        strong_share=("is_strong", "mean"),
        strength_score=("strength_raw", "mean"),
    ).reset_index()
    zones["direction_score"] = (
        100.0 * zones["mean_body_points"] / zones["mean_range_points"].clip(lower=0.1)
    )
    zones["structure_score"] = 100.0 * (zones["trend_share"] - zones["chop_share"])
    zones["volatility_score"] = 100.0 * (
        zones["expansion_share"] - zones["compression_share"]
    )

    zones["direction_conviction"] = percentile(zones["direction_score"].abs())
    zones["trend_propensity"] = percentile(zones["trend_share"])
    zones["activity_propensity"] = percentile(zones["expansion_share"])
    zones["strength_propensity"] = percentile(zones["strength_score"])
    components = [
        "direction_conviction",
        "trend_propensity",
        "activity_propensity",
        "strength_propensity",
    ]
    zones["overlap_count"] = (zones[components] >= 0.65).sum(axis=1)
    zones["overlap_score"] = 100.0 * np.power(
        zones[components].clip(lower=0.01).prod(axis=1), 0.25
    )
    zones["overlap_direction"] = np.sign(zones["direction_score"])
    zones["resolution_min"] = minutes
    zones["day"] = zones["dow_index"].map(dict(enumerate(DAYS)))
    zones["time"] = zones["slot"].map(
        lambda slot: f"{slot * minutes // 60:02d}:{slot * minutes % 60:02d}"
    )

    slots = 24 * 60 // minutes
    matrices = {}
    matrix_columns = [
        "direction_score", "structure_score", "volatility_score", "strength_score",
        "overlap_score", "overlap_count", "count", "bull_share", "bear_share",
        "neutral_share", "trend_share", "chop_share", "range_share",
        "expansion_share", "compression_share", "normal_vol_share", "strong_share",
        "mean_body_points", "mean_range_points",
    ]
    indexed = zones.set_index(["dow_index", "slot"])
    full_index = pd.MultiIndex.from_product(
        [range(5), range(slots)], names=["dow_index", "slot"]
    )
    indexed = indexed.reindex(full_index)
    for column in matrix_columns:
        values = indexed[column].to_numpy().reshape(5, slots)
        matrices[column] = [
            [None if pd.isna(value) else round(float(value), 4) for value in row]
            for row in values
        ]
    matrices["labels"] = [
        f"{slot * minutes // 60:02d}:{slot * minutes % 60:02d}"
        for slot in range(slots)
    ]
    return matrices, zones


def legacy_comparison(frame: pd.DataFrame) -> dict:
    legacy_path = Path("/mnt/c/Users/cmake/Documents/MarketData/EURUSD_M5_2025_bars.csv")
    result = {
        "legacy_file": str(legacy_path),
        "legacy_exists": legacy_path.exists(),
        "authoritative_rows": int(len(frame)),
        "authoritative_start": str(frame.index.min()),
        "authoritative_end": str(frame.index.max()),
    }
    if not legacy_path.exists():
        return result
    legacy = pd.read_csv(legacy_path, parse_dates=["datetime"])
    result.update(
        {
            "legacy_rows": int(len(legacy)),
            "legacy_start": str(legacy["datetime"].min()),
            "legacy_end": str(legacy["datetime"].max()),
            "legacy_timezone_warning": (
                "timestamps match the broker-derived series but the old HTML labels them UTC"
            ),
        }
    )
    return result


def html_document(payload: dict, comparison: dict) -> str:
    data = json.dumps(payload, separators=(",", ":"))
    meta = json.dumps(comparison, separators=(",", ":"))
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>EURUSD MARKET_MAP Historical Zones</title>
<style>
*{{box-sizing:border-box}} body{{margin:0;background:#0d1117;color:#c9d1d9;font:13px 'Segoe UI',sans-serif;padding:18px}}
h1{{font-size:18px;color:#f0f6fc;margin:0 0 4px}} .sub{{color:#8b949e;font-size:11px;margin-bottom:14px}}
.note,.panel,.cards>div{{background:#161b22;border:1px solid #30363d;border-radius:7px}}
.note{{padding:11px 14px;line-height:1.65;margin-bottom:13px}} .warn{{color:#d29922}}
.ctrl{{display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin:12px 0}}
button{{padding:6px 12px;border:1px solid #30363d;border-radius:5px;background:#161b22;color:#8b949e;cursor:pointer}}
button.on{{background:#1f6feb;color:white;border-color:#388bfd}} .sep{{width:1px;height:22px;background:#30363d;margin:0 5px}}
.panel{{padding:14px;margin-bottom:14px}} .wrap{{overflow-x:auto}} table{{border-collapse:collapse}}
th{{font-size:9px;color:#6e7681;padding:3px 1px;min-width:30px}} td.day{{min-width:94px;color:#8b949e;font-weight:600;padding-right:10px}}
td.cell{{height:38px;min-width:30px;text-align:center;border:1px solid #0d1117;font-size:9px;font-weight:700;position:relative}}
td.cell:hover{{outline:2px solid #ffffffaa;z-index:2}} h2{{font-size:12px;color:#f0f6fc;margin:0 0 10px}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:9px;margin-bottom:14px}}
.cards>div{{padding:10px 12px}} .cards b{{display:block;color:#f0f6fc;margin-bottom:4px}} .cards span{{font-size:11px;color:#8b949e;line-height:1.45}}
#tip{{display:none;position:fixed;z-index:5;pointer-events:none;background:#1c2128;border:1px solid #484f58;border-radius:6px;padding:10px 13px;line-height:1.65;min-width:245px;font-size:11px}}
.legend{{font-size:10px;color:#8b949e;margin-top:10px}} .green{{color:#3fb950}} .red{{color:#f85149}} .blue{{color:#58a6ff}}
</style>
</head>
<body>
<h1>EURUSD MARKET_MAP Historical Day × Time Zones</h1>
<div class="sub">DST-corrected UTC · calibrated EURUSD M5 panel · calendar year 2025 · trailing-state labels only</div>
<div class="note"><b>Four map dimensions plus overlap:</b> direction is historical M5 displacement efficiency;
structure compares trend versus chop frequency; volatility compares expansion versus compression;
strength measures normalized directional displacement × path efficiency. The overlap map highlights
zones ranking in the top 35% on multiple dimensions. Structure and strength are related and should
not be counted as fully independent confirmations.</div>
<div class="note warn" id="legacy"></div>
<div class="cards">
 <div><b>Direction</b><span>Green bullish, red bearish. Score = mean candle body / mean candle range.</span></div>
 <div><b>Structure</b><span>Green trend-dominant, red chop-dominant, grey range-balanced.</span></div>
 <div><b>Volatility</b><span>Orange/red expansion-dominant, blue compression-dominant.</span></div>
 <div><b>Strength</b><span>0–100 normalized displacement and path efficiency over the trailing hour.</span></div>
 <div><b>Overlap</b><span>Brightness is four-way percentile overlap; cell text is dimensions above the 65th percentile.</span></div>
</div>
<div class="ctrl">
 <button id="r60" onclick="setRes(60)">Hourly</button><button id="r30" onclick="setRes(30)">30 min</button>
 <div class="sep"></div>
 <button id="mdirection" onclick="setMetric('direction')">Direction</button>
 <button id="mstructure" onclick="setMetric('structure')">Structure</button>
 <button id="mvolatility" onclick="setMetric('volatility')">Volatility</button>
 <button id="mstrength" onclick="setMetric('strength')">Strength</button>
 <button id="moverlap" onclick="setMetric('overlap')">Overlap</button>
</div>
<div class="panel"><h2 id="title"></h2><div class="wrap"><table id="map"></table></div><div class="legend" id="legend"></div></div>
<div id="tip"></div>
<script>
const DATA={data}; const META={meta}; const DAYS={json.dumps(DAYS)};
let res=60, metric='direction'; const tip=document.getElementById('tip');
const clamp=(x,a,b)=>Math.max(a,Math.min(b,x)); const rgb=(r,g,b)=>`rgb(${{r}},${{g}},${{b}})`;
function diverge(v,pos,neg,scale=35){{let t=clamp(Math.abs(v)/scale,0,1);let base=[33,38,45], c=v>=0?pos:neg;return rgb(...base.map((x,i)=>Math.round(x+(c[i]-x)*t)));}}
function bg(v){{
 if(v==null)return '#0d1117';
 if(metric==='direction')return diverge(v,[35,134,54],[192,57,43],18);
 if(metric==='structure')return diverge(v,[35,134,54],[163,47,47],45);
 if(metric==='volatility')return diverge(v,[210,110,25],[31,111,190],45);
 if(metric==='strength'){{let t=clamp(v/55,0,1);return rgb(Math.round(33+177*t),Math.round(38+72*t),Math.round(45-20*t));}}
 let t=clamp(v/85,0,1);return rgb(Math.round(33+20*t),Math.round(38+130*t),Math.round(45+35*t));
}}
function pct(v){{return v==null?'—':(100*v).toFixed(1)+'%';}}
function build(){{
 const d=DATA[String(res)], labels=d.labels, key=metric+'_score', mat=d[key], table=document.getElementById('map');table.innerHTML='';
 let tr=table.insertRow(), blank=document.createElement('th');tr.appendChild(blank);
 labels.forEach((x,i)=>{{let th=document.createElement('th');th.textContent=res===60?x.replace(':00','h'):(i%2===0?x.slice(0,2):'');tr.appendChild(th);}});
 for(let r=0;r<5;r++){{let row=table.insertRow(), dl=row.insertCell();dl.className='day';dl.textContent=DAYS[r];
  for(let c=0;c<labels.length;c++){{let td=row.insertCell();td.className='cell';let v=mat[r][c];td.style.background=bg(v);
   if(metric==='overlap')td.textContent=v==null?'':Math.round(d.overlap_count[r][c]);
   else if(v!=null && (metric==='strength'||Math.abs(v)>=5))td.textContent=Math.round(v);
   td.onmouseenter=e=>show(e,r,c);td.onmousemove=e=>move(e);td.onmouseleave=()=>tip.style.display='none';
  }}
 }}
 const names={{direction:'Directional efficiency',structure:'Trend minus chop share',volatility:'Expansion minus compression share',strength:'Historical strength',overlap:'Four-map overlap'}};
 document.getElementById('title').textContent=names[metric]+' · '+(res===60?'hourly':'30-minute')+' UTC zones';
 document.getElementById('legend').innerHTML=metric==='overlap'?'Cell number = count of direction, trend, expansion and strength dimensions above their 65th percentile.':'Scores summarize historical tendencies, not a forecast for every occurrence.';
 document.querySelectorAll('button').forEach(b=>b.classList.remove('on'));document.getElementById('r'+res).classList.add('on');document.getElementById('m'+metric).classList.add('on');
}}
function show(e,r,c){{const d=DATA[String(res)], label=d.labels[c], lines=[
 `<b>${{DAYS[r]}} · ${{label}} UTC</b>`,
 `Direction: ${{d.direction_score[r][c]?.toFixed(1)??'—'}}`,
 `Bull / Bear / Neutral: ${{pct(d.bull_share[r][c])}} / ${{pct(d.bear_share[r][c])}} / ${{pct(d.neutral_share[r][c])}}`,
 `Structure score: ${{d.structure_score[r][c]?.toFixed(1)??'—'}}`,
 `Trend / Chop / Range: ${{pct(d.trend_share[r][c])}} / ${{pct(d.chop_share[r][c])}} / ${{pct(d.range_share[r][c])}}`,
 `Volatility score: ${{d.volatility_score[r][c]?.toFixed(1)??'—'}}`,
 `Expansion / Compression / Normal: ${{pct(d.expansion_share[r][c])}} / ${{pct(d.compression_share[r][c])}} / ${{pct(d.normal_vol_share[r][c])}}`,
 `Strength: ${{d.strength_score[r][c]?.toFixed(1)??'—'}} · strong trend share ${{pct(d.strong_share[r][c])}}`,
 `Overlap: ${{d.overlap_count[r][c]??'—'}}/4 · score ${{d.overlap_score[r][c]?.toFixed(1)??'—'}}`,
 `Bars: ${{Math.round(d.count[r][c]||0)}}`];tip.innerHTML=lines.join('<br>');tip.style.display='block';move(e);}}
function move(e){{tip.style.left=(e.clientX+14)+'px';tip.style.top=(e.clientY-10)+'px';}}
function setRes(x){{res=x;build();}} function setMetric(x){{metric=x;build();}}
document.getElementById('legacy').textContent=`Legacy check: old map used ${{META.legacy_rows||'unknown'}} bars from ${{META.legacy_start||'unknown'}} to ${{META.legacy_end||'unknown'}} and cannot be reproduced as a full-year UTC map. This page uses ${{META.authoritative_rows}} calibrated UTC bars.`;
build();
</script>
</body></html>"""


def markdown_frame(frame: pd.DataFrame, include_index: bool = True) -> str:
    display = frame.copy()
    if include_index:
        display.insert(0, "metric", display.index.astype(str))
    columns = [str(column) for column in display.columns]
    rows = [
        "| " + " | ".join(columns) + " |",
        "|" + "|".join("---" for _ in columns) + "|",
    ]
    for values in display.itertuples(index=False, name=None):
        rows.append("| " + " | ".join(str(value) for value in values) + " |")
    return "\n".join(rows)


def write_report(
    zones: pd.DataFrame, comparison: dict, output: Path, html_path: Path
) -> None:
    hourly = zones[zones["resolution_min"] == 60].copy()
    correlations = hourly[
        ["direction_score", "trend_share", "expansion_share", "strength_score"]
    ].corr(method="spearman")
    top = hourly.sort_values(["overlap_count", "overlap_score"], ascending=False).head(15)
    lines = [
        "# MARKET_MAP Historical Heatmap Study",
        "",
        "Four historical day/time maps were generated from the DST-corrected",
        "calibrated EURUSD M5 panel for calendar year 2025.",
        "",
        f"- Interactive HTML: `{html_path}`",
        f"- Authoritative rows: {comparison['authoritative_rows']:,}",
        f"- Period: {comparison['authoritative_start']} through {comparison['authoritative_end']}",
        "",
        "## Legacy Direction Map Check",
        "",
        f"- Legacy source: `{comparison.get('legacy_file')}`",
        f"- Legacy rows: {comparison.get('legacy_rows', 'unavailable')}",
        f"- Legacy period: {comparison.get('legacy_start', 'unavailable')} through "
        f"{comparison.get('legacy_end', 'unavailable')}",
        "- The legacy map is partial-year and its timestamps were labelled UTC without",
        "  the broker/Dukascopy DST alignment contract. It is retained for comparison,",
        "  but the regenerated calibrated UTC map is authoritative.",
        "",
        "## Map Definitions",
        "",
        "- Direction: mean M5 candle body divided by mean M5 range, scaled to -100..100.",
        "- Structure: trend share minus chop share.",
        "- Volatility: expansion share minus compression share.",
        "- Strength: normalized trailing-hour displacement multiplied by path efficiency.",
        "- Overlap: number of dimensions above the 65th percentile across all 120",
        "  weekday/hour zones; overlap score is their geometric-mean percentile.",
        "",
        "## Cross-Map Spearman Correlation",
        "",
        markdown_frame(correlations.round(3)),
        "",
        "Correlation measures whether whole maps overlap generally. Individual high-value",
        "zones can overlap even when the global correlation is modest.",
        "",
        "Structure trend share and strength are strongly related (`rho=0.880`), so their",
        "agreement is not two fully independent confirmations. Direction is nearly independent",
        "of structure, volatility and strength; zones where direction also aligns are therefore",
        "the more informative overlaps.",
        "",
        "## Strongest Hourly Overlap Zones",
        "",
        markdown_frame(
            top[
                [
                    "day", "time", "direction_score", "trend_share",
                    "expansion_share", "strength_score", "overlap_count", "overlap_score",
                ]
            ].round(3),
            include_index=False,
        ),
        "",
        "These are historical priors, not standalone trade signals.",
    ]
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--panel", type=Path, default=DEFAULT_PANEL)
    parser.add_argument("--html", type=Path, default=DEFAULT_HTML)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    frame = pd.read_csv(args.panel, index_col=0, parse_dates=True).sort_index()
    if frame.index.tz is not None:
        frame.index = frame.index.tz_convert("UTC").tz_localize(None)
    frame = causalize_panel(frame)
    observed = current_path(frame)
    labels = label_axes(observed).add_prefix("current_")
    frame = frame.join(observed).join(labels)
    frame = frame[
        (frame.index >= pd.Timestamp("2025-01-01"))
        & (frame.index < pd.Timestamp("2026-01-01"))
        & (frame.index.dayofweek < 5)
    ].dropna(subset=list(observed.columns) + list(labels.columns))

    payload = {}
    outputs = []
    for minutes in (60, 30):
        matrices, zones = build_resolution(frame, minutes)
        payload[str(minutes)] = matrices
        outputs.append(zones)
    all_zones = pd.concat(outputs, ignore_index=True)
    comparison = legacy_comparison(frame)

    args.html.parent.mkdir(parents=True, exist_ok=True)
    args.html.write_text(html_document(payload, comparison), encoding="utf-8")
    all_zones.to_csv(args.csv, index=False, float_format="%.6f")
    write_report(all_zones, comparison, args.report, args.html)
    print("bars:", len(frame))
    print("html:", args.html)
    print("zones:", args.csv)
    print("report:", args.report)


if __name__ == "__main__":
    main()
