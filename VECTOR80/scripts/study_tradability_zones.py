#!/usr/bin/env python3
"""Find recurring EURUSD day/time zones that are easier to trade."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

try:
    from scripts.study_market_regimes import causalize_panel, current_path, label_axes
except ModuleNotFoundError:
    from study_market_regimes import causalize_panel, current_path, label_axes


ROOT = Path(__file__).resolve().parents[1]
PANEL = Path("/home/cmake/VectorShared/research/EURUSD_M5_CALIBRATED_PANEL.csv.gz")
OUT = ROOT / "generated" / "MARKET_MAP_tradability_zones.csv"
REPORT = ROOT / "generated" / "MARKET_MAP_TRADABILITY_STUDY.md"
HTML = ROOT / "generated" / "EURUSD_MARKET_MAP_TRADABILITY.html"
PIP = 0.0001
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]


def first_hit(
    favorable: np.ndarray, adverse: np.ndarray, target: np.ndarray, stop: np.ndarray
) -> np.ndarray:
    target_hit = favorable >= target[:, None]
    stop_hit = adverse >= stop[:, None]
    target_first = np.where(target_hit.any(1), target_hit.argmax(1), 999)
    stop_first = np.where(stop_hit.any(1), stop_hit.argmax(1), 999)
    return target_first < stop_first


def add_forward_outcomes(frame: pd.DataFrame, bars: int = 6) -> pd.DataFrame:
    """Evaluate causal continuation and reversal signals over the next 30 minutes."""
    out = frame.copy()
    highs = np.column_stack([out["high"].shift(-i) for i in range(1, bars + 1)])
    lows = np.column_stack([out["low"].shift(-i) for i in range(1, bars + 1)])
    closes = np.column_stack([out["close"].shift(-i) for i in range(1, bars + 1)])
    entry = out["close"].to_numpy()
    direction = out["current_direction_label"].map(
        {"BULL": 1.0, "BEAR": -1.0, "NEUTRAL": 0.0}
    ).to_numpy()
    atr = out["atr14_pips"].clip(lower=1.0).to_numpy()
    spread = out["spread_avg"].clip(lower=0.0, upper=3.0).to_numpy()
    target = np.maximum(3.0, atr)
    stop = np.maximum(2.0, atr * 0.75)

    valid_future = ~np.isnan(highs).all(axis=1) & ~np.isnan(lows).all(axis=1)
    safe_highs = np.where(np.isnan(highs), -np.inf, highs)
    safe_lows = np.where(np.isnan(lows), np.inf, lows)
    future_high = np.max(safe_highs, axis=1)
    future_low = np.min(safe_lows, axis=1)
    future_high[~valid_future] = np.nan
    future_low[~valid_future] = np.nan
    up_mfe = (future_high - entry) / PIP - spread
    up_mae = (entry - future_low) / PIP + spread
    down_mfe = (entry - future_low) / PIP - spread
    down_mae = (future_high - entry) / PIP + spread
    cont_mfe = np.where(direction > 0, up_mfe, np.where(direction < 0, down_mfe, np.nan))
    cont_mae = np.where(direction > 0, up_mae, np.where(direction < 0, down_mae, np.nan))
    rev_mfe = np.where(direction > 0, down_mfe, np.where(direction < 0, up_mfe, np.nan))
    rev_mae = np.where(direction > 0, down_mae, np.where(direction < 0, up_mae, np.nan))

    up_fav = (highs - entry[:, None]) / PIP - spread[:, None]
    up_adv = (entry[:, None] - lows) / PIP + spread[:, None]
    down_fav = (entry[:, None] - lows) / PIP - spread[:, None]
    down_adv = (highs - entry[:, None]) / PIP + spread[:, None]
    cont_fav = np.where(direction[:, None] > 0, up_fav, down_fav)
    cont_adv = np.where(direction[:, None] > 0, up_adv, down_adv)
    rev_fav = np.where(direction[:, None] > 0, down_fav, up_fav)
    rev_adv = np.where(direction[:, None] > 0, down_adv, up_adv)
    valid_direction = direction != 0

    out["continuation_mfe"] = cont_mfe
    out["continuation_mae"] = cont_mae
    out["reversal_mfe"] = rev_mfe
    out["reversal_mae"] = rev_mae
    out["continuation_win"] = first_hit(cont_fav, cont_adv, target, stop) & valid_direction
    out["reversal_win"] = first_hit(rev_fav, rev_adv, target, stop) & valid_direction
    out["continuation_edge"] = np.where(
        out["continuation_win"], target - spread, -np.minimum(cont_mae, stop) - spread
    )
    out["reversal_edge"] = np.where(
        out["reversal_win"], target - spread, -np.minimum(rev_mae, stop) - spread
    )
    out["future_abs_move"] = np.abs(closes[:, -1] - entry) / PIP
    out["future_path"] = np.nansum(
        np.abs(np.diff(np.column_stack([entry, closes]), axis=1)) / PIP, axis=1
    )
    out["future_cleanliness"] = out["future_abs_move"] / out["future_path"].clip(lower=0.1)
    out["future_valid"] = ~np.isnan(closes).any(axis=1)
    return out


def prepare_frame(panel: Path) -> pd.DataFrame:
    frame = pd.read_csv(panel, index_col=0, parse_dates=True).sort_index()
    if frame.index.tz is not None:
        frame.index = frame.index.tz_convert("UTC").tz_localize(None)
    frame = causalize_panel(frame)
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


def aggregate(frame: pd.DataFrame, period: str, resolution_min: int) -> pd.DataFrame:
    if period == "DEV":
        sample = frame[
            (frame.index >= "2025-01-01") & (frame.index < "2026-01-01")
            & frame["future_valid"]
        ]
    else:
        sample = frame[(frame.index >= "2026-03-01") & frame["future_valid"]]
    sample = sample.copy()
    sample["slot"] = (
        sample.index.hour * 60 + sample.index.minute
    ) // resolution_min
    sample["time"] = sample["slot"].map(
        lambda x: f"{x * resolution_min // 60:02d}:{x * resolution_min % 60:02d}"
    )
    grouped = sample.groupby(["dow_index", "slot", "day", "time"], observed=True)
    zones = grouped.agg(
        rows=("close", "size"),
        tick_count=("tick_count", "mean"),
        tick_volume=("tick_volume", "mean"),
        bid_volume=("bid_volume", "mean"),
        ask_volume=("ask_volume", "mean"),
        spread_avg=("spread_avg", "mean"),
        spread_atr=("spread_atr", "mean"),
        max_tick_interval_ms=("max_tick_interval_ms", "median"),
        imbalance_abs=("imbalance", lambda x: x.abs().mean()),
        liquidity_score=("liquidity_score_bar", "mean"),
        clean_move_share=("future_cleanliness", lambda x: (x >= 0.45).mean()),
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
    zones["period"] = period
    zones["resolution_min"] = resolution_min
    return zones


def rank_dev(dev: pd.DataFrame) -> pd.DataFrame:
    out = dev.copy()
    out["continuation_quality"] = (
        0.35 * out["continuation_win_rate"].rank(pct=True)
        + 0.30 * out["continuation_edge"].rank(pct=True)
        + 0.20 * out["clean_move_share"].rank(pct=True)
        + 0.15 * out["liquidity_score"].rank(pct=True)
    ) * 100.0
    out["reversal_quality"] = (
        0.35 * out["reversal_win_rate"].rank(pct=True)
        + 0.30 * out["reversal_edge"].rank(pct=True)
        + 0.20 * out["clean_move_share"].rank(pct=True)
        + 0.15 * out["liquidity_score"].rank(pct=True)
    ) * 100.0
    out["best_quality"] = out[["continuation_quality", "reversal_quality"]].max(axis=1)
    out["strategy_fit"] = np.where(
        out["continuation_quality"] >= out["reversal_quality"], "CONTINUATION", "REVERSAL"
    )
    out.loc[out["best_quality"] < 55.0, "strategy_fit"] = "AVOID"

    cluster_features = [
        "tick_count", "spread_atr", "liquidity_score", "future_cleanliness",
        "future_abs_move", "continuation_edge", "reversal_edge",
    ]
    scaled = StandardScaler().fit_transform(out[cluster_features])
    out["cluster"] = KMeans(n_clusters=5, random_state=42, n_init=20).fit_predict(scaled)
    return out


def stable_zones(dev: pd.DataFrame, oos: pd.DataFrame) -> pd.DataFrame:
    joined = dev.merge(
        oos,
        on=["dow_index", "slot", "day", "time", "resolution_min"],
        suffixes=("_dev", "_oos"),
    )
    joined["strategy_fit_dev"] = joined["strategy_fit"]
    joined["best_quality_dev"] = joined["best_quality"]
    joined["selected_edge_dev"] = np.where(
        joined["strategy_fit_dev"].eq("CONTINUATION"),
        joined["continuation_edge_dev"],
        joined["reversal_edge_dev"],
    )
    joined["selected_edge_oos"] = np.where(
        joined["strategy_fit_dev"].eq("CONTINUATION"),
        joined["continuation_edge_oos"],
        joined["reversal_edge_oos"],
    )
    joined["selected_wr_oos"] = np.where(
        joined["strategy_fit_dev"].eq("CONTINUATION"),
        joined["continuation_win_rate_oos"],
        joined["reversal_win_rate_oos"],
    )
    joined["stable_positive"] = (
        joined["strategy_fit_dev"].ne("AVOID")
        & (joined["selected_edge_dev"] > 0)
        & (joined["selected_edge_oos"] > 0)
    )
    return joined


def add_parent_confirmation(stable: pd.DataFrame) -> pd.DataFrame:
    out = stable.copy()
    out["parent_30m_positive"] = False
    out["parent_30m_strategy"] = ""
    parents = out[out["resolution_min"] == 30]
    lookup = {
        (row.day, row.time): (bool(row.stable_positive), row.strategy_fit_dev)
        for row in parents.itertuples()
    }
    for index, row in out[out["resolution_min"] == 15].iterrows():
        hour, minute = map(int, row["time"].split(":"))
        parent_time = f"{hour:02d}:{(minute // 30) * 30:02d}"
        positive, strategy = lookup.get((row["day"], parent_time), (False, ""))
        out.at[index, "parent_30m_positive"] = positive
        out.at[index, "parent_30m_strategy"] = strategy
    out["robust_zone"] = (
        out["stable_positive"]
        & (
            out["resolution_min"].eq(30)
            | (
                out["parent_30m_positive"]
                & out["strategy_fit_dev"].eq(out["parent_30m_strategy"])
            )
        )
    )
    return out


def markdown(frame: pd.DataFrame) -> str:
    columns = list(frame.columns)
    lines = [
        "| " + " | ".join(columns) + " |",
        "|" + "|".join("---" for _ in columns) + "|",
    ]
    for row in frame.itertuples(index=False, name=None):
        lines.append("| " + " | ".join(str(value) for value in row) + " |")
    return "\n".join(lines)


def write_report(zones: pd.DataFrame, stable: pd.DataFrame, output: Path) -> None:
    primary = stable[stable["resolution_min"] == 15]
    candidates = primary[primary["stable_positive"]].copy()
    robust = candidates[candidates["robust_zone"]].copy()
    robust = robust.sort_values("selected_edge_oos", ascending=False)
    top = robust[
        [
            "day", "time", "strategy_fit_dev", "best_quality_dev",
            "liquidity_score_dev", "selected_edge_dev", "selected_edge_oos",
            "selected_wr_oos", "rows_oos",
        ]
    ].head(20).round(3)
    dev = zones[(zones["period"] == "DEV") & (zones["resolution_min"] == 15)]
    oos = zones[(zones["period"] == "OOS") & (zones["resolution_min"] == 15)]
    stable_30 = stable[
        (stable["resolution_min"] == 30) & stable["stable_positive"]
    ]
    lines = [
        "# MARKET_MAP Advanced Tradability-Zone Study",
        "",
        "This study asks whether recurring weekday/15-minute zones are historically",
        "easier to trade after estimated spread, rather than merely active.",
        "",
        "## Inputs",
        "",
        "- Tick count and calibrated bid/ask volume.",
        "- Average spread relative to ATR and maximum tick gap.",
        "- Forward 30-minute path cleanliness and absolute movement.",
        "- Target-before-stop outcomes for continuation and reversal archetypes.",
        "- Development: calendar 2025. OOS validation: March-June 2026.",
        "",
        "## Strategy Archetypes",
        "",
        "- Continuation follows the causal trailing-hour BULL/BEAR state.",
        "- Reversal trades against that state.",
        "- Dynamic target is `max(3 pips, 1.0 x ATR14)`.",
        "- Dynamic stop is `max(2 pips, 0.75 x ATR14)`.",
        "- Spread is deducted and target must be reached before stop.",
        "",
        "## Result",
        "",
        f"- Primary 15-minute development zones: {len(dev)}",
        f"- Primary 15-minute OOS zones: {len(oos)}",
        f"- Positive in development and OOS using the development-selected archetype: "
        f"{len(candidates)}",
        f"- Confirmed by a positive 30-minute parent with the same archetype: "
        f"{len(robust)}",
        f"- Stable positive 30-minute zones used as a robustness check: {len(stable_30)}",
        "",
        "## Robust 15-Minute Zones",
        "",
        markdown(top) if len(top) else "No zones passed.",
        "",
        "## Interpretation",
        "",
        "- Raw volume identifies activity, not tradeability.",
        "- High volume with wide spread or low path cleanliness is often difficult.",
        "- A useful zone requires movement, liquidity, acceptable cost and a strategy",
        "  archetype that remains positive out of sample.",
        "- Only zones whose 30-minute parent validates with the same strategy are",
        "  treated as robust. Other positive 15-minute cells remain provisional.",
        "- Each 15-minute OOS cell currently contains only about 39-42 observations.",
        "  Because 472 zones were examined, multiple-testing risk remains substantial.",
        "- Require a second forward period or live shadow validation before these zones",
        "  can change entry thresholds or position size.",
        "- Zone filters are priors. They must refine a valid setup, not create entries.",
    ]
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def html_document(stable: pd.DataFrame) -> str:
    stable = stable[stable["resolution_min"] == 15].copy()
    fields = [
        "day", "time", "strategy_fit_dev", "best_quality_dev", "liquidity_score_dev",
        "tick_count_dev", "tick_volume_dev", "bid_volume_dev", "ask_volume_dev",
        "spread_avg_dev", "spread_atr_dev", "future_cleanliness_dev",
        "continuation_edge_dev", "continuation_edge_oos", "reversal_edge_dev",
        "reversal_edge_oos", "selected_edge_dev", "selected_edge_oos",
        "selected_wr_oos", "stable_positive", "rows_dev", "rows_oos",
        "parent_30m_positive", "parent_30m_strategy", "robust_zone",
    ]
    payload = stable[fields].to_dict(orient="records")
    data = json.dumps(payload, separators=(",", ":"))
    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
<title>EURUSD Advanced Tradability Zones</title><style>
body{{background:#0d1117;color:#c9d1d9;font:13px Segoe UI,sans-serif;padding:18px}}
h1{{font-size:18px;color:#f0f6fc}} .note{{background:#161b22;border:1px solid #30363d;border-radius:7px;padding:11px;margin:10px 0;line-height:1.6}}
button{{padding:6px 12px;margin:0 4px 10px 0;border:1px solid #30363d;border-radius:5px;background:#161b22;color:#8b949e;cursor:pointer}}
button.on{{background:#1f6feb;color:white;border-color:#388bfd}}
table{{border-collapse:collapse;background:#161b22}} th{{font-size:9px;color:#6e7681;min-width:30px;padding:3px}}
td{{border:1px solid #0d1117;height:39px;min-width:30px;text-align:center;font-size:9px;font-weight:700}}
td.day{{min-width:90px;color:#8b949e;text-align:left;padding-left:6px}} td.cell:hover{{outline:2px solid #fff9}}
#tip{{display:none;position:fixed;background:#1c2128;border:1px solid #484f58;border-radius:6px;padding:10px;z-index:4;pointer-events:none;line-height:1.6}}
.wrap{{overflow-x:auto}} .good{{color:#3fb950}} .bad{{color:#f85149}}
</style></head><body><h1>EURUSD Advanced Tradability Zones</h1>
<div class="note">Each 15-minute weekday zone is ranked on liquidity, clean movement and target-before-stop performance.
Bright green cells remained positive in March-June 2026 and have a positive 30-minute parent with the same strategy.
Amber cells are positive at 15 minutes but lack 30-minute confirmation.
The 30-minute aggregation is retained in the research table as a robustness check.
Red zones failed OOS or are historical avoid zones. This is more specific than session filtering.</div>
<div><button id="btradability" onclick="setView('tradability')">Tradability</button>
<button id="bvolume" onclick="setView('volume')">Tick Volume</button>
<button id="bliquidity" onclick="setView('liquidity')">Liquidity</button>
<button id="bspread" onclick="setView('spread')">Spread / ATR</button>
<button id="bcleanliness" onclick="setView('cleanliness')">Path Cleanliness</button></div>
<div class="wrap"><table id="t"></table></div><div id="tip"></div>
<script>const D={data}, DAYS={DAYS!r};const tip=document.getElementById('tip'),by={{}};let view='tradability';
D.forEach(x=>by[x.day+'|'+x.time]=x);let t=document.getElementById('t'),r=t.insertRow();r.appendChild(document.createElement('th'));
for(let i=0;i<96;i++){{let h=document.createElement('th');h.textContent=i%4===0?String(i/4).padStart(2,'0'):'';r.appendChild(h)}}
function shade(q,a,b){{q=Math.max(0,Math.min(1,q));return`rgb(${{Math.round(a[0]+q*(b[0]-a[0]))}},${{Math.round(a[1]+q*(b[1]-a[1]))}},${{Math.round(a[2]+q*(b[2]-a[2]))}})`}}
function bg(x){{if(!x)return'#0d1117';if(view==='volume')return shade((x.tick_volume_dev-50)/750,[20,35,55],[190,95,25]);if(view==='liquidity')return shade(x.liquidity_score_dev/100,[35,30,50],[35,160,85]);if(view==='spread')return shade(x.spread_atr_dev/0.35,[25,80,130],[190,45,40]);if(view==='cleanliness')return shade((x.future_cleanliness_dev-.15)/.35,[70,35,45],[30,150,70]);if(x.robust_zone){{let q=Math.min(1,Math.max(0,x.selected_edge_oos/2));return`rgb(${{20}},${{90+120*q}},${{45}})`}}if(x.stable_positive)return'#8a6d1d';let q=Math.min(1,Math.max(0,(55-x.best_quality_dev)/30));return`rgb(${{75+90*q}},${{35}},${{40}})`}}
function txt(x){{if(!x)return'';if(view==='volume')return Math.round(x.tick_volume_dev);if(view==='liquidity')return Math.round(x.liquidity_score_dev);if(view==='spread')return x.spread_atr_dev.toFixed(2);if(view==='cleanliness')return x.future_cleanliness_dev.toFixed(2);return x.strategy_fit_dev==='CONTINUATION'?'C':x.strategy_fit_dev==='REVERSAL'?'R':'—'}}
let cells=[];
DAYS.forEach(day=>{{let tr=t.insertRow(),d=tr.insertCell();d.className='day';d.textContent=day;for(let i=0;i<96;i++){{let mins=i*15,tm=String(Math.floor(mins/60)).padStart(2,'0')+':'+String(mins%60).padStart(2,'0'),x=by[day+'|'+tm],c=tr.insertCell();c.className='cell';cells.push([c,x]);c.style.background=bg(x);c.textContent=txt(x);c.onmouseenter=e=>{{if(!x)return;tip.innerHTML=`<b>${{day}} ${{tm}} UTC · ${{x.strategy_fit_dev}}</b><br>2025 quality: ${{x.best_quality_dev.toFixed(1)}}<br>Liquidity: ${{x.liquidity_score_dev.toFixed(1)}} · ticks ${{x.tick_count_dev.toFixed(0)}}<br>Tick volume: ${{x.tick_volume_dev.toFixed(0)}} · bid/ask ${{x.bid_volume_dev.toFixed(0)}}/${{x.ask_volume_dev.toFixed(0)}}<br>Spread: ${{x.spread_avg_dev.toFixed(2)}} · spread/ATR ${{x.spread_atr_dev.toFixed(3)}}<br>Path cleanliness: ${{x.future_cleanliness_dev.toFixed(3)}}<br>Continuation edge DEV/OOS: ${{x.continuation_edge_dev.toFixed(2)}} / ${{x.continuation_edge_oos.toFixed(2)}} pips<br>Reversal edge DEV/OOS: ${{x.reversal_edge_dev.toFixed(2)}} / ${{x.reversal_edge_oos.toFixed(2)}} pips<br><b>Selected OOS edge: ${{x.selected_edge_oos.toFixed(2)}} · WR ${{(100*x.selected_wr_oos).toFixed(1)}}%</b><br>30m confirmation: ${{x.parent_30m_positive?x.parent_30m_strategy:'NO'}}<br>Class: ${{x.robust_zone?'ROBUST':x.stable_positive?'PROVISIONAL':'AVOID/FAILED'}}<br>Rows DEV/OOS: ${{x.rows_dev}}/${{x.rows_oos}}`;tip.style.display='block';tip.style.left=e.clientX+12+'px';tip.style.top=e.clientY-8+'px'}};c.onmousemove=e=>{{tip.style.left=e.clientX+12+'px';tip.style.top=e.clientY-8+'px'}};c.onmouseleave=()=>tip.style.display='none'}}}});
function setView(v){{view=v;cells.forEach(([c,x])=>{{c.style.background=bg(x);c.textContent=txt(x)}});document.querySelectorAll('button').forEach(b=>b.classList.remove('on'));document.getElementById('b'+v).classList.add('on')}}setView('tradability');
</script></body></html>"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--panel", type=Path, default=PANEL)
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--report", type=Path, default=REPORT)
    parser.add_argument("--html", type=Path, default=HTML)
    args = parser.parse_args()

    frame = prepare_frame(args.panel)
    zone_outputs = []
    stable_outputs = []
    for resolution_min in (15, 30):
        dev = rank_dev(aggregate(frame, "DEV", resolution_min))
        oos = aggregate(frame, "OOS", resolution_min)
        zone_outputs.extend([dev, oos])
        stable_outputs.append(stable_zones(dev, oos))
    zones = pd.concat(zone_outputs, ignore_index=True)
    stable = add_parent_confirmation(pd.concat(stable_outputs, ignore_index=True))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    zones.to_csv(args.out, index=False, float_format="%.6f")
    stable.to_csv(args.out.with_name("MARKET_MAP_tradability_validation.csv"), index=False)
    write_report(zones, stable, args.report)
    args.html.write_text(html_document(stable), encoding="utf-8")
    for resolution_min in (15, 30):
        selected = stable["resolution_min"] == resolution_min
        print(
            f"stable positive {resolution_min}m zones:",
            int(stable.loc[selected, "stable_positive"].sum()),
        )
    print(
        "robust 15m zones:",
        int(
            stable.loc[stable["resolution_min"].eq(15), "robust_zone"].sum()
        ),
    )
    print("report:", args.report)
    print("html:", args.html)


if __name__ == "__main__":
    main()
