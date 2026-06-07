#!/usr/bin/env python3
"""Build one original-style Historical Zones document for 2023-2025."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

try:
    from scripts.build_market_map_heatmaps import DAYS, build_resolution
    from scripts.study_market_regimes import causalize_panel, current_path, label_axes
    from scripts.validate_tradability_historical_holdout import prepare_adjusted_frame
except ModuleNotFoundError:
    from build_market_map_heatmaps import DAYS, build_resolution
    from study_market_regimes import causalize_panel, current_path, label_axes
    from validate_tradability_historical_holdout import prepare_adjusted_frame


ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = Path(
    "/home/cmake/VectorShared/research/dukascopy/EURUSD/2023_2024/broker_adjusted"
)
PANEL_2025 = Path("/home/cmake/VectorShared/research/EURUSD_M5_CALIBRATED_PANEL.csv.gz")
DEFAULT_HTML = ROOT / "generated" / "EURUSD_MARKET_MAP_HISTORICAL_ZONES_2023_2025.html"
DEFAULT_CSV = ROOT / "generated" / "MARKET_MAP_historical_zones_2023_2025.csv"


def state_frame(frame: pd.DataFrame, year: int) -> pd.DataFrame:
    observed_columns = [
        "current_net_atr",
        "current_efficiency",
        "current_range_atr",
        "current_range_expansion",
        "current_up_excursion_atr",
        "current_down_excursion_atr",
    ]
    label_columns = [
        "current_direction_label",
        "current_structure_label",
        "current_volatility_label",
        "current_regime_label",
    ]
    if not set(observed_columns + label_columns).issubset(frame.columns):
        observed = current_path(frame)
        labels = label_axes(observed).add_prefix("current_")
        frame = frame.join(observed).join(labels)
    return frame[
        (frame.index >= pd.Timestamp(f"{year}-01-01"))
        & (frame.index < pd.Timestamp(f"{year + 1}-01-01"))
        & (frame.index.dayofweek < 5)
    ].dropna(subset=observed_columns + label_columns)


def load_year(year: int, archive: Path, panel_2025: Path) -> pd.DataFrame:
    if year in (2023, 2024):
        path = archive / f"EURUSD_M5_broker_adjusted_{year}.csv.gz"
        return state_frame(prepare_adjusted_frame(path), year)
    frame = pd.read_csv(panel_2025, index_col=0, parse_dates=True).sort_index()
    if frame.index.tz is not None:
        frame.index = frame.index.tz_convert("UTC").tz_localize(None)
    return state_frame(causalize_panel(frame), year)


def html_document(payload: dict, metadata: dict) -> str:
    data = json.dumps(payload, separators=(",", ":"))
    meta = json.dumps(metadata, separators=(",", ":"))
    days = json.dumps(DAYS)
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>EURUSD MARKET_MAP Historical Zones 2023-2025</title>
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
.legend{{font-size:10px;color:#8b949e;margin-top:10px}}
</style></head><body>
<h1>EURUSD MARKET_MAP Historical Day × Time Zones</h1>
<div class="sub">DST-corrected UTC · parity-calibrated EURUSD M5 panels · calendar years 2023, 2024 and 2025 · trailing-state labels only</div>
<div class="note"><b>Four map dimensions plus overlap:</b> direction is historical M5 displacement efficiency;
structure compares trend versus chop frequency; volatility compares expansion versus compression;
strength measures normalized directional displacement × path efficiency. The overlap map highlights
zones ranking in the top 35% on multiple dimensions. Structure and strength are related and should
not be counted as fully independent confirmations.</div>
<div class="note warn">The 15-minute view is primary. Five-minute cells have about one observation per weekday per week and are therefore a noisier exploratory layer. Compare broad neighboring blocks, not isolated 5-minute cells.</div>
<div class="cards">
 <div><b>Direction</b><span>Green bullish, red bearish. Score = mean candle body / mean candle range.</span></div>
 <div><b>Structure</b><span>Green trend-dominant, red chop-dominant, grey range-balanced.</span></div>
 <div><b>Volatility</b><span>Orange/red expansion-dominant, blue compression-dominant.</span></div>
 <div><b>Strength</b><span>0–100 normalized displacement and path efficiency over the trailing hour.</span></div>
 <div><b>Overlap</b><span>Brightness is four-way percentile overlap; cell text is dimensions above the 65th percentile.</span></div>
</div>
<div class="ctrl">
 <button id="y2023" onclick="setYear(2023)">2023</button>
 <button id="y2024" onclick="setYear(2024)">2024</button>
 <button id="y2025" onclick="setYear(2025)">2025</button>
 <div class="sep"></div>
 <button id="r15" onclick="setRes(15)">15 min</button>
 <button id="r5" onclick="setRes(5)">5 min</button>
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
const DATA={data}, META={meta}, DAYS={days};
let year=2025,res=15,metric='direction';const tip=document.getElementById('tip');
const clamp=(x,a,b)=>Math.max(a,Math.min(b,x));const rgb=(r,g,b)=>`rgb(${{r}},${{g}},${{b}})`;
function diverge(v,pos,neg,scale=35){{let t=clamp(Math.abs(v)/scale,0,1),base=[33,38,45],c=v>=0?pos:neg;return rgb(...base.map((x,i)=>Math.round(x+(c[i]-x)*t)));}}
function bg(v){{if(v==null)return'#0d1117';if(metric==='direction')return diverge(v,[35,134,54],[192,57,43],18);if(metric==='structure')return diverge(v,[35,134,54],[163,47,47],45);if(metric==='volatility')return diverge(v,[210,110,25],[31,111,190],45);if(metric==='strength'){{let t=clamp(v/55,0,1);return rgb(Math.round(33+177*t),Math.round(38+72*t),Math.round(45-20*t));}}let t=clamp(v/85,0,1);return rgb(Math.round(33+20*t),Math.round(38+130*t),Math.round(45+35*t));}}
function pct(v){{return v==null?'—':(100*v).toFixed(1)+'%';}}
function build(){{const d=DATA[String(year)][String(res)],labels=d.labels,key=metric+'_score',mat=d[key],table=document.getElementById('map');table.innerHTML='';
 let tr=table.insertRow();tr.appendChild(document.createElement('th'));
 labels.forEach((x,i)=>{{let th=document.createElement('th');th.textContent=res===15?(i%4===0?x.slice(0,2):''):(i%12===0?x.slice(0,2):'');tr.appendChild(th);}});
 for(let r=0;r<5;r++){{let row=table.insertRow(),dl=row.insertCell();dl.className='day';dl.textContent=DAYS[r];for(let c=0;c<labels.length;c++){{let td=row.insertCell();td.className='cell';let v=mat[r][c];td.style.background=bg(v);if(metric==='overlap')td.textContent=v==null?'':Math.round(d.overlap_count[r][c]);else if(v!=null&&(metric==='strength'||Math.abs(v)>=5))td.textContent=Math.round(v);td.onmouseenter=e=>show(e,r,c);td.onmousemove=e=>move(e);td.onmouseleave=()=>tip.style.display='none';}}}}
 const names={{direction:'Directional efficiency',structure:'Trend minus chop share',volatility:'Expansion minus compression share',strength:'Historical strength',overlap:'Four-map overlap'}};
 document.getElementById('title').textContent=names[metric]+' · '+year+' · '+res+'-minute UTC zones';
 document.getElementById('legend').textContent=(res===5?'Higher-noise 5-minute exploratory layer. ':'Primary 15-minute layer. ')+(metric==='overlap'?'Cell number = dimensions above their annual 65th percentile.':'Scores summarize historical tendencies, not a forecast for every occurrence.');
 document.querySelectorAll('button').forEach(b=>b.classList.remove('on'));document.getElementById('y'+year).classList.add('on');document.getElementById('r'+res).classList.add('on');document.getElementById('m'+metric).classList.add('on');}}
function show(e,r,c){{const d=DATA[String(year)][String(res)],label=d.labels[c],lines=[`<b>${{year}} · ${{DAYS[r]}} · ${{label}} UTC</b>`,`Direction: ${{d.direction_score[r][c]?.toFixed(1)??'—'}}`,`Bull / Bear / Neutral: ${{pct(d.bull_share[r][c])}} / ${{pct(d.bear_share[r][c])}} / ${{pct(d.neutral_share[r][c])}}`,`Structure score: ${{d.structure_score[r][c]?.toFixed(1)??'—'}}`,`Trend / Chop / Range: ${{pct(d.trend_share[r][c])}} / ${{pct(d.chop_share[r][c])}} / ${{pct(d.range_share[r][c])}}`,`Volatility score: ${{d.volatility_score[r][c]?.toFixed(1)??'—'}}`,`Expansion / Compression / Normal: ${{pct(d.expansion_share[r][c])}} / ${{pct(d.compression_share[r][c])}} / ${{pct(d.normal_vol_share[r][c])}}`,`Strength: ${{d.strength_score[r][c]?.toFixed(1)??'—'}} · strong trend share ${{pct(d.strong_share[r][c])}}`,`Overlap: ${{d.overlap_count[r][c]??'—'}}/4 · score ${{d.overlap_score[r][c]?.toFixed(1)??'—'}}`,`Bars: ${{Math.round(d.count[r][c]||0)}}`];tip.innerHTML=lines.join('<br>');tip.style.display='block';move(e);}}
function move(e){{tip.style.left=(e.clientX+14)+'px';tip.style.top=(e.clientY-10)+'px';}}
function setYear(x){{year=x;build();}}function setRes(x){{res=x;build();}}function setMetric(x){{metric=x;build();}}build();
</script></body></html>"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, default=ARCHIVE)
    parser.add_argument("--panel-2025", type=Path, default=PANEL_2025)
    parser.add_argument("--html", type=Path, default=DEFAULT_HTML)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    args = parser.parse_args()

    payload = {}
    outputs = []
    metadata = {}
    for year in (2023, 2024, 2025):
        frame = load_year(year, args.archive, args.panel_2025)
        payload[str(year)] = {}
        metadata[str(year)] = {
            "rows": int(len(frame)),
            "start": str(frame.index.min()),
            "end": str(frame.index.max()),
        }
        for minutes in (15, 5):
            matrices, zones = build_resolution(frame, minutes)
            payload[str(year)][str(minutes)] = matrices
            zones["year"] = year
            outputs.append(zones)
    all_zones = pd.concat(outputs, ignore_index=True)
    args.html.parent.mkdir(parents=True, exist_ok=True)
    args.html.write_text(html_document(payload, metadata), encoding="utf-8")
    all_zones.to_csv(args.csv, index=False, float_format="%.6f")
    print(json.dumps(metadata, indent=2))
    print("html:", args.html)
    print("zones:", args.csv)


if __name__ == "__main__":
    main()
