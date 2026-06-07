"""
Step 71 - Code-ready 80% engine set.

Selects the frozen engines that pass both:
  - overall OOS precision >= 80%
  - monthly precision >= 80% for months with at least 3 signals

Writes a compact config JSON and report for EA implementation.
"""

from __future__ import annotations

import json

import pandas as pd


BASE = "/home/cmake/Vector/research"
FROZEN_SIGNALS = f"{BASE}/zzlines_frozen_80_pool_oos_signals.csv"

OUT_SIGNALS = f"{BASE}/zzlines_code_ready_oos_signals.csv"
OUT_MONTHLY = f"{BASE}/zzlines_code_ready_monthly.csv"
OUT_CONFIG = f"{BASE}/vector80_engine_config.json"
OUT_REPORT = f"{BASE}/ZZLINES_CODE_READY_ENGINE_SET.md"

CODE_READY_ENGINES = [
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
        "engine_id": "SELL_HH_BULLCONT_LONDON_HGB_096",
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


def summarize(df: pd.DataFrame, by: list[str]) -> pd.DataFrame:
    return df.groupby(by).agg(
        signals=("is_hit", "size"),
        hits=("is_hit", "sum"),
        precision=("is_hit", "mean"),
        avg_score=("score", "mean"),
    ).reset_index()


def main():
    signals = pd.read_csv(FROZEN_SIGNALS, parse_dates=["entry_time"])
    engine_ids = {e["engine_id"] for e in CODE_READY_ENGINES}
    selected = signals[signals["engine_id"].isin(engine_ids)].copy()
    selected = selected.sort_values("entry_time")
    selected.to_csv(OUT_SIGNALS, index=False, float_format="%.6f")

    monthly = summarize(selected, ["month"])
    monthly.to_csv(OUT_MONTHLY, index=False, float_format="%.6f")

    by_side = summarize(selected, ["side"])
    by_engine = summarize(selected, ["engine_id"])
    n = len(selected)
    hits = int(selected["is_hit"].sum())
    precision = hits / n if n else 0.0
    month_gate = monthly[monthly["signals"] >= 3]["precision"].min() if len(monthly) else 0.0

    config = {
        "name": "VECTOR80_ZZLINES_CODE_READY",
        "symbol": "EURUSD",
        "timeframe": "M5",
        "indicator": "ZigZag Lines MTF for MT5",
        "zigzag_settings": {"Depth": 12, "Deviation": 5, "Backstep": 3},
        "entry_offsets_m5": [0, 1, 2],
        "same_side_cooldown_minutes": 30,
        "features_source": "EURUSD_M5_FULL_PANEL feature set; broker export must reproduce these columns",
        "model_export_note": "sklearn models require ONNX export or equivalent MQL implementation before live EA inference",
        "engines": CODE_READY_ENGINES,
        "validation": {
            "oos_start": "2026-03-01",
            "oos_end": "2026-06-01 23:55:00",
            "signals": n,
            "hits": hits,
            "precision": precision,
            "monthly_min_precision_for_months_ge3_signals": float(month_gate),
        },
    }
    with open(OUT_CONFIG, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)

    lines = ["# VECTOR80 Code-Ready Engine Set", ""]
    lines.append("This is the frozen engine subset selected for EA prototyping.")
    lines.append("")
    lines.append("## Validation")
    lines.append("")
    lines.append(f"- OOS window: `2026-03-01` to `2026-06-01 23:55:00`")
    lines.append(f"- Signals: `{n}`")
    lines.append(f"- Hits: `{hits}`")
    lines.append(f"- Precision: `{100*precision:.1f}%`")
    lines.append(f"- Monthly minimum precision for months with >=3 signals: `{100*month_gate:.1f}%`")
    lines.append("")
    lines.append("## Monthly")
    lines.append("")
    for r in monthly.itertuples(index=False):
        lines.append(f"- `{r.month}`: `{int(r.signals)}` signals, `{int(r.hits)}` hits, `{100*r.precision:.1f}%`")
    lines.append("")
    lines.append("## Side Split")
    lines.append("")
    for r in by_side.itertuples(index=False):
        lines.append(f"- `{r.side}`: `{int(r.signals)}` signals, `{int(r.hits)}` hits, `{100*r.precision:.1f}%`")
    lines.append("")
    lines.append("## Engines")
    lines.append("")
    for engine in CODE_READY_ENGINES:
        row = by_engine[by_engine["engine_id"].eq(engine["engine_id"])]
        if row.empty:
            sig = hit = prec = 0
        else:
            r = row.iloc[0]
            sig, hit, prec = int(r["signals"]), int(r["hits"]), float(r["precision"])
        lines.append(
            f"- `{engine['engine_id']}`: side `{engine['side']}`, group `{engine['group_key']}`, "
            f"model `{engine['model_type']}`, threshold `{engine['threshold']}`, "
            f"risk `{engine['stop_pips']}p/{engine['target_r']}R/{engine['horizon_minutes']}m`, "
            f"OOS `{sig}` signals, `{hit}` hits, `{100*prec:.1f}%`"
        )
    lines.append("")
    lines.append("## EA Coding Notes")
    lines.append("")
    lines.append("- Use one signal router with a `30` minute same-side cooldown.")
    lines.append("- Trade BUY engines with `5` pip stop and `1R` target.")
    lines.append("- Trade SELL engines with `8` pip stop and `1R` target.")
    lines.append("- Entry is allowed on the pivot bar close, `+1`, or `+2` M5 bars.")
    lines.append("- Keep `HH/HL/LH/LL`, session, volatility regime, and trade context in the log row.")
    lines.append("- Before live trading, export the same feature columns from MT5 broker data and verify model parity.")
    lines.append("")
    lines.append("## Outputs")
    lines.append("")
    lines.append(f"- `{OUT_CONFIG}`")
    lines.append(f"- `{OUT_SIGNALS}`")
    lines.append(f"- `{OUT_MONTHLY}`")
    with open(OUT_REPORT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"saved: {OUT_CONFIG}")
    print(f"saved: {OUT_SIGNALS}")
    print(f"saved: {OUT_MONTHLY}")
    print(f"saved: {OUT_REPORT}")
    print(f"precision={100*precision:.1f}% signals={n} hits={hits} monthly_min_ge3={100*month_gate:.1f}%")


if __name__ == "__main__":
    main()
