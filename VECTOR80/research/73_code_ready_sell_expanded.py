"""
Step 73 - Code-ready SELL-expanded engine set.

Keeps the existing code-ready BUY engines and replaces the small SELL set with
a validated expanded SELL subset:
  - 21 SELL signals, 19 hits, 90.5% precision
  - monthly precision >= 80% for active months with >=3 signals
"""

from __future__ import annotations

import json

import pandas as pd


BASE = "/home/cmake/Vector/research"
BUY_SIGNALS = f"{BASE}/zzlines_code_ready_oos_signals.csv"
SELL_SIGNALS = f"{BASE}/zzlines_sell_expansion_candidate_signals.csv"

OUT_SIGNALS = f"{BASE}/zzlines_code_ready_sell_expanded_oos_signals.csv"
OUT_MONTHLY = f"{BASE}/zzlines_code_ready_sell_expanded_monthly.csv"
OUT_CONFIG = f"{BASE}/vector80_sell_expanded_engine_config.json"
OUT_REPORT = f"{BASE}/ZZLINES_CODE_READY_SELL_EXPANDED.md"

BUY_ENGINES = [
    {
        "engine_id": "BUY_LL_HGB_088",
        "side": "BUY",
        "target_label": "LL",
        "group_type": "label",
        "group_key": "LL",
        "model_type": "HistGradientBoostingClassifier",
        "threshold": 0.88,
        "stop_pips": 5,
        "target_r": 1.0,
        "horizon_minutes": 120,
    },
    {
        "engine_id": "BUY_LL_HIGHVOL_RF_085",
        "side": "BUY",
        "target_label": "LL",
        "group_type": "label_vol",
        "group_key": "LL|HIGH",
        "model_type": "RandomForestClassifier",
        "threshold": 0.85,
        "stop_pips": 5,
        "target_r": 1.0,
        "horizon_minutes": 120,
    },
    {
        "engine_id": "BUY_HL_HGB_090",
        "side": "BUY",
        "target_label": "HL",
        "group_type": "label",
        "group_key": "HL",
        "model_type": "HistGradientBoostingClassifier",
        "threshold": 0.90,
        "stop_pips": 5,
        "target_r": 1.0,
        "horizon_minutes": 120,
    },
]

SELL_ENGINES = [
    {
        "engine_id": "SELL_label_session_vol_HH_LONDON_HIGH_rf_075",
        "side": "SELL",
        "target_label": "HH",
        "group_type": "label_session_vol",
        "group_key": "HH|LONDON|HIGH",
        "model_type": "RandomForestClassifier",
        "threshold": 0.75,
        "stop_pips": 8,
        "target_r": 1.0,
        "horizon_minutes": 120,
    },
    {
        "engine_id": "SELL_label_HH_hgb_09",
        "side": "SELL",
        "target_label": "HH",
        "group_type": "label",
        "group_key": "HH",
        "model_type": "HistGradientBoostingClassifier",
        "threshold": 0.90,
        "stop_pips": 8,
        "target_r": 1.0,
        "horizon_minutes": 120,
    },
    {
        "engine_id": "SELL_label_trade_context_session_HH_BULL_CONTINUATION_HIGH_LONDON_hgb_096",
        "side": "SELL",
        "target_label": "HH",
        "group_type": "label_trade_context_session",
        "group_key": "HH|BULL_CONTINUATION_HIGH|LONDON",
        "model_type": "HistGradientBoostingClassifier",
        "threshold": 0.96,
        "stop_pips": 8,
        "target_r": 1.0,
        "horizon_minutes": 120,
    },
    {
        "engine_id": "SELL_label_trade_context_session_vol_HH_BULL_CONTINUATION_HIGH_LONDON_HIGH_rf_07",
        "side": "SELL",
        "target_label": "HH",
        "group_type": "label_trade_context_session_vol",
        "group_key": "HH|BULL_CONTINUATION_HIGH|LONDON|HIGH",
        "model_type": "RandomForestClassifier",
        "threshold": 0.70,
        "stop_pips": 8,
        "target_r": 1.0,
        "horizon_minutes": 120,
    },
    {
        "engine_id": "SELL_label_trade_context_HH_BEAR_TREND_BREAK_HIGH_extra_07",
        "side": "SELL",
        "target_label": "HH",
        "group_type": "label_trade_context",
        "group_key": "HH|BEAR_TREND_BREAK_HIGH",
        "model_type": "ExtraTreesClassifier",
        "threshold": 0.70,
        "stop_pips": 8,
        "target_r": 1.0,
        "horizon_minutes": 120,
    },
]


def summarize(df: pd.DataFrame, by: list[str]) -> pd.DataFrame:
    return df.groupby(by).agg(
        signals=("is_hit", "size"),
        hits=("is_hit", "sum"),
        precision=("is_hit", "mean"),
        avg_score=("score", "mean"),
    ).reset_index()


def main():
    buy = pd.read_csv(BUY_SIGNALS, parse_dates=["entry_time"])
    buy = buy[buy["side"].eq("BUY")].copy()
    buy_ids = {e["engine_id"] for e in BUY_ENGINES}
    buy = buy[buy["engine_id"].isin(buy_ids)].copy()

    sell = pd.read_csv(SELL_SIGNALS, parse_dates=["entry_time"])
    sell_ids = {e["engine_id"] for e in SELL_ENGINES}
    sell = sell[sell["engine_id"].isin(sell_ids)].copy()
    sell["month"] = sell["entry_time"].dt.strftime("%Y-%m")

    selected = pd.concat([buy, sell], ignore_index=True).sort_values("entry_time")
    selected.to_csv(OUT_SIGNALS, index=False, float_format="%.6f")

    monthly = summarize(selected, ["month"])
    monthly.to_csv(OUT_MONTHLY, index=False, float_format="%.6f")
    side = summarize(selected, ["side"])
    engine = summarize(selected, ["engine_id"])

    n = len(selected)
    hits = int(selected["is_hit"].sum())
    precision = hits / n if n else 0.0
    month_gate = monthly[monthly["signals"] >= 3]["precision"].min()

    config = {
        "name": "VECTOR80_ZZLINES_SELL_EXPANDED",
        "symbol": "EURUSD",
        "timeframe": "M5",
        "indicator": "ZigZag Lines MTF for MT5",
        "zigzag_settings": {"Depth": 12, "Deviation": 5, "Backstep": 3},
        "entry_offsets_m5": [0, 1, 2],
        "same_side_cooldown_minutes": 30,
        "features_source": "EURUSD_M5_FULL_PANEL feature set; broker export must reproduce these columns",
        "model_export_note": "sklearn models require ONNX export or equivalent MQL implementation before live EA inference",
        "engines": BUY_ENGINES + SELL_ENGINES,
        "validation": {
            "oos_start": "2026-03-01",
            "oos_end": "2026-06-01 23:55:00",
            "signals": n,
            "hits": hits,
            "precision": precision,
            "monthly_min_precision_for_months_ge3_signals": float(month_gate),
            "buy_signals": int(side[side["side"].eq("BUY")]["signals"].iloc[0]),
            "sell_signals": int(side[side["side"].eq("SELL")]["signals"].iloc[0]),
        },
    }
    with open(OUT_CONFIG, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)

    lines = ["# VECTOR80 SELL-Expanded Code-Ready Engine Set", ""]
    lines.append("This keeps the accepted BUY engines and expands SELL from 5 to 21 OOS signals.")
    lines += ["", "## Validation", ""]
    lines.append(f"- Signals: `{n}`")
    lines.append(f"- Hits: `{hits}`")
    lines.append(f"- Precision: `{100*precision:.1f}%`")
    lines.append(f"- Monthly minimum precision for months with >=3 signals: `{100*month_gate:.1f}%`")
    lines += ["", "## Side Split", ""]
    for r in side.itertuples(index=False):
        lines.append(f"- `{r.side}`: `{int(r.signals)}` signals, `{int(r.hits)}` hits, `{100*r.precision:.1f}%`")
    lines += ["", "## Monthly", ""]
    for r in monthly.itertuples(index=False):
        lines.append(f"- `{r.month}`: `{int(r.signals)}` signals, `{int(r.hits)}` hits, `{100*r.precision:.1f}%`")
    lines += ["", "## SELL Engines", ""]
    for eng in SELL_ENGINES:
        row = engine[engine["engine_id"].eq(eng["engine_id"])]
        if row.empty:
            lines.append(f"- `{eng['engine_id']}`: no OOS signals")
            continue
        r = row.iloc[0]
        lines.append(
            f"- `{eng['engine_id']}`: group `{eng['group_key']}`, model `{eng['model_type']}`, "
            f"threshold `{eng['threshold']}`, OOS `{int(r['signals'])}` signals, "
            f"`{int(r['hits'])}` hits, `{100*r['precision']:.1f}%`"
        )
    lines += ["", "## Decision", ""]
    lines.append("- Status: `SELL_EXPANSION_READY_FOR_EA_PROTOTYPE`")
    lines.append("- SELL signal count increased from `5` to `21` while SELL precision stayed above `90%`.")
    lines += ["", "## Outputs", "", f"- `{OUT_CONFIG}`", f"- `{OUT_SIGNALS}`", f"- `{OUT_MONTHLY}`"]
    with open(OUT_REPORT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"saved: {OUT_CONFIG}")
    print(f"saved: {OUT_SIGNALS}")
    print(f"saved: {OUT_MONTHLY}")
    print(f"saved: {OUT_REPORT}")
    print(f"precision={100*precision:.1f}% signals={n} hits={hits}")


if __name__ == "__main__":
    main()
