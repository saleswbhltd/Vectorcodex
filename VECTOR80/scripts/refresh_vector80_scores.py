#!/usr/bin/env python3
"""
Refresh VECTOR80_model_scores.csv from a fresh broker tick export.

This implements Option 1 for VECTOR80: keep the EA in CSV-score mode, but
generate new score rows for recent broker/demo pivots. It intentionally refuses
to fabricate scores if required broker tick data or feature rows are missing.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesClassifier, HistGradientBoostingClassifier, RandomForestClassifier


ROOT = Path("/home/cmake/Vectorcodex/VECTOR80")
RESEARCH = ROOT / "research"
COMMON = Path("/mnt/c/Users/cmake/AppData/Roaming/MetaQuotes/Terminal/Common/Files")
PIP = 0.0001
DEV_START = pd.Timestamp("2025-06-02")
DEV_END = pd.Timestamp("2026-02-28 23:59:59")
ENTRY_OFFSETS = [0, 1, 2]
SIDE_CONFIG = {
    "BUY": {"labels": ["HL", "LL"], "stop": 5, "rr": 1.0, "horizon": 24},
    "SELL": {"labels": ["HH", "LH"], "stop": 8, "rr": 1.0, "horizon": 24},
}


@dataclass(frozen=True)
class EngineSpec:
    engine_id: str
    side: str
    label: str
    group_type: str
    group_key: str
    model: str
    threshold: float


ENGINES = [
    EngineSpec("BUY_LL_HGB_088", "BUY", "LL", "label", "LL", "hgb", 0.88),
    EngineSpec("BUY_LL_HIGHVOL_RF_085", "BUY", "LL", "label_vol", "LL|HIGH", "rf", 0.85),
    EngineSpec("BUY_HL_HGB_090", "BUY", "HL", "label", "HL", "hgb", 0.90),
    EngineSpec("SELL_label_session_vol_HH_LONDON_HIGH_rf_075", "SELL", "HH", "label_session_vol", "HH|LONDON|HIGH", "rf", 0.75),
    EngineSpec("SELL_label_HH_hgb_09", "SELL", "HH", "label", "HH", "hgb", 0.90),
    EngineSpec("SELL_label_trade_context_session_HH_BULL_CONTINUATION_HIGH_LONDON_hgb_096", "SELL", "HH", "label_trade_context_session", "HH|BULL_CONTINUATION_HIGH|LONDON", "hgb", 0.96),
    EngineSpec("SELL_label_trade_context_session_vol_HH_BULL_CONTINUATION_HIGH_LONDON_HIGH_rf_07", "SELL", "HH", "label_trade_context_session_vol", "HH|BULL_CONTINUATION_HIGH|LONDON|HIGH", "rf", 0.70),
    EngineSpec("SELL_label_trade_context_HH_BEAR_TREND_BREAK_HIGH_extra_07", "SELL", "HH", "label_trade_context", "HH|BEAR_TREND_BREAK_HIGH", "extra", 0.70),
]
ENGINE_BY_ID = {e.engine_id: e for e in ENGINES}


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def group_cols(group_type: str) -> list[str]:
    return {
        "label": ["label"],
        "label_vol": ["label", "vol_regime"],
        "label_session_vol": ["label", "session", "vol_regime"],
        "label_trade_context": ["label", "trade_context"],
        "label_trade_context_session": ["label", "trade_context", "session"],
        "label_trade_context_session_vol": ["label", "trade_context", "session", "vol_regime"],
    }[group_type]


def join_key(df: pd.DataFrame, cols: list[str]) -> pd.Series:
    return df[cols].astype(str).agg("|".join, axis=1)


def model_for(name: str):
    if name == "hgb":
        return HistGradientBoostingClassifier(
            max_iter=700,
            learning_rate=0.03,
            max_leaf_nodes=24,
            max_depth=6,
            min_samples_leaf=24,
            l2_regularization=0.25,
            early_stopping=True,
            validation_fraction=0.15,
            n_iter_no_change=50,
            random_state=42,
        )
    if name == "rf":
        return RandomForestClassifier(
            n_estimators=650,
            max_depth=11,
            min_samples_leaf=14,
            class_weight="balanced_subsample",
            n_jobs=-1,
            random_state=42,
        )
    if name == "extra":
        return ExtraTreesClassifier(
            n_estimators=800,
            max_depth=12,
            min_samples_leaf=10,
            class_weight="balanced",
            n_jobs=-1,
            random_state=42,
        )
    raise ValueError(name)


def read_ticks(path: Path) -> pd.DataFrame:
    ticks = pd.read_csv(path, parse_dates=["datetime"])
    if ticks.empty:
        raise SystemExit(f"tick export is empty: {path}")
    ticks["datetime"] = pd.to_datetime(ticks["datetime"]).dt.tz_localize(None)
    ticks = ticks.sort_values("datetime").reset_index(drop=True)
    ticks = ticks[ticks["mid"].astype(float) > 0].copy()
    if ticks.empty:
        raise SystemExit(f"tick export has no usable mid prices: {path}")
    return ticks


def half_profile(group: pd.DataFrame) -> pd.Series:
    n = len(group)
    if n < 4:
        return pd.Series({"vel1": np.nan, "vel2": np.nan, "run_up": np.nan, "run_dn": np.nan, "at_high_pct": np.nan, "at_low_pct": np.nan})
    half = n // 2
    v1 = group["mid_change_pips"].iloc[:half].sum() / half
    v2 = group["mid_change_pips"].iloc[half:].sum() / (n - half)
    mid = group["mid"].to_numpy(float)
    cummax = np.maximum.accumulate(mid)
    cummin = np.minimum.accumulate(mid)
    run_up = float(np.max((cummax - cummin[0]) / PIP))
    run_dn = float(np.max((cummax[0] - cummin) / PIP))
    high = group["mid"].max()
    low = group["mid"].min()
    at_high = ((high - group["mid"]) / PIP <= 1.0).mean() * 100
    at_low = ((group["mid"] - low) / PIP <= 1.0).mean() * 100
    return pd.Series({"vel1": v1, "vel2": v2, "run_up": run_up, "run_dn": run_dn, "at_high_pct": at_high, "at_low_pct": at_low})


def build_broker_panel(ticks: pd.DataFrame) -> pd.DataFrame:
    ticks = ticks.copy()
    ticks["bar_time"] = ticks["datetime"].dt.floor("5min")
    ticks["mid_change_pips"] = ticks["mid"].diff().abs() / PIP
    ticks["spread_pips"] = (ticks["ask"] - ticks["bid"]) / PIP
    ticks["bid_change"] = ticks["bid"].diff()
    ticks["ask_change"] = ticks["ask"].diff()
    ticks["bid_up"] = (ticks["bid_change"] > 0).astype(int)
    ticks["ask_down"] = (ticks["ask_change"] < 0).astype(int)
    ticks["time_delta_ms"] = ticks["datetime"].diff().dt.total_seconds() * 1000

    g = ticks.groupby("bar_time", sort=True)
    bars = g["mid"].agg(open="first", high="max", low="min", close="last")
    bars["tick_volume"] = g.size()
    bars["bid_volume"] = 0.0
    bars["ask_volume"] = 0.0

    feats = pd.DataFrame(index=bars.index)
    feats["tick_count"] = g.size()
    feats["median_tick_interval_ms"] = g["time_delta_ms"].median()
    feats["max_tick_interval_ms"] = g["time_delta_ms"].max()
    feats["spread_avg"] = g["spread_pips"].mean()
    feats["spread_max"] = g["spread_pips"].max()
    feats["bid_aggressor_pct"] = 100 * g["bid_up"].mean()
    feats["ask_aggressor_pct"] = 100 * g["ask_down"].mean()
    feats["imbalance"] = feats["bid_aggressor_pct"] - feats["ask_aggressor_pct"]
    feats["bar_high"] = g["mid"].max()
    feats["bar_low"] = g["mid"].min()
    prof = g.apply(half_profile, include_groups=False)
    feats["tick_velocity_first_half"] = prof["vel1"]
    feats["tick_velocity_second_half"] = prof["vel2"]
    feats["vel_ratio_2nd_to_1st"] = prof["vel2"] / prof["vel1"].replace(0, np.nan)
    feats["max_run_up_pips_intrabar"] = prof["run_up"]
    feats["max_run_dn_pips_intrabar"] = prof["run_dn"]
    feats["ticks_at_high_pct"] = prof["at_high_pct"]
    feats["ticks_at_low_pct"] = prof["at_low_pct"]
    return bars.join(feats)


def add_m5_indicators(df: pd.DataFrame) -> pd.DataFrame:
    step35 = load_module(RESEARCH / "35_build_full_panel.py", "step35")
    return step35.add_m5_indicators(df.copy())


def add_h1_from_m5(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.index.name = "datetime"
    h1 = df[["open", "high", "low", "close"]].resample("1h").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    h1_path = ROOT / "scripts" / "_vector80_live_h1_tmp.csv"
    h1.reset_index(names="datetime").to_csv(h1_path, index=False)
    step35 = load_module(RESEARCH / "35_build_full_panel.py", "step35_h1")
    try:
        return step35.add_h1_features(df, str(h1_path))
    finally:
        h1_path.unlink(missing_ok=True)


def load_event_candidates(events_path: Path, day: str | None) -> pd.DataFrame:
    rows = []
    with events_path.open(newline="") as f:
        for r in csv.DictReader(f):
            if r.get("event") != "BLOCK_MODEL_SCORE" or r.get("note") != "missing_external_score":
                continue
            if day and not r["time"].startswith(day.replace("-", ".")):
                continue
            if r.get("engine_id") not in ENGINE_BY_ID:
                continue
            rows.append(r)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["event_time"] = pd.to_datetime(df["time"], format="%Y.%m.%d %H:%M:%S")
    df["bar_time"] = df["event_time"].dt.floor("5min")
    df["pivot_time"] = pd.to_datetime(df["pivot_time"], format="%Y.%m.%d %H:%M:%S")
    df["pivot_price"] = df["pivot_price"].astype(float)
    return df.drop_duplicates(["bar_time", "engine_id"], keep="last").sort_values(["bar_time", "engine_id"])


def live_pivots_from_events(events: pd.DataFrame) -> pd.DataFrame:
    if events.empty:
        return pd.DataFrame(columns=["pivot_time", "price", "side", "label"])
    out = events[["pivot_time", "pivot_price", "label"]].drop_duplicates().copy()
    out["price"] = out.pop("pivot_price")
    out["side"] = np.where(out["label"].isin(["HH", "LH"]), "HIGH", "LOW")
    return out[["pivot_time", "price", "side", "label"]]


def build_catalog_in_memory(pivots: pd.DataFrame, outcomes: pd.DataFrame) -> pd.DataFrame:
    piv = pivots[pivots["label"].isin(["HH", "HL", "LH", "LL"])].copy()
    piv["side_trade"] = piv["label"].map({"HL": "BUY", "LL": "BUY", "HH": "SELL", "LH": "SELL"})
    piv["practical_stop"] = piv["side_trade"].map(lambda s: SIDE_CONFIG[s]["stop"])
    piv["practical_rr"] = 1.0
    piv["practical_horizon"] = 24

    best_rows = []
    for _, cfg in SIDE_CONFIG.items():
        sub = outcomes[
            outcomes["label"].isin(cfg["labels"])
            & outcomes["entry_offset"].isin(ENTRY_OFFSETS)
            & outcomes["stop_buffer_pips"].eq(cfg["stop"])
            & outcomes["rr_target"].eq(cfg["rr"])
            & outcomes["horizon_bars"].eq(cfg["horizon"])
        ].copy()
        agg = sub.groupby("pivot_time").agg(
            practical_tradable=("tradable", "max"),
            max_mfe_pips=("mfe_pips", "max"),
            min_mae_pips=("mae_pips", "min"),
            max_r_multiple=("r_multiple", "max"),
        )
        first_offsets = []
        for pt, g in sub.groupby("pivot_time"):
            good = g[g["tradable"]].sort_values("entry_offset")
            first_offsets.append((pt, int((good if not good.empty else g).iloc[0]["entry_offset"])))
        offs = pd.DataFrame(first_offsets, columns=["pivot_time", "best_entry_offset"]).set_index("pivot_time")
        best_rows.append(agg.join(offs, how="left"))

    all_agg = pd.concat(best_rows).reset_index()
    cat = piv.merge(all_agg, on="pivot_time", how="left")
    cat["practical_tradable"] = cat["practical_tradable"].fillna(False).astype(bool)
    cat["best_entry_offset"] = cat["best_entry_offset"].fillna(0).astype(int)
    return cat


def build_training_data():
    step64 = load_module(RESEARCH / "64_buy_sell_precision_refine.py", "step64")
    panel = pd.read_csv(RESEARCH / "EURUSD_M5_FULL_PANEL.csv.gz", index_col=0, parse_dates=True).loc[:DEV_END].copy()
    pivots = pd.read_csv(RESEARCH / "zzlines_pivot_map_enriched.csv", parse_dates=["pivot_time"])
    outcomes = pd.read_csv(RESEARCH / "zzlines_pivot_entry_outcomes.csv", parse_dates=["pivot_time", "entry_time", "hit_time"])
    rules = pd.read_csv(RESEARCH / "zzlines_greedy_cover_summary.csv")
    cat = build_catalog_in_memory(pivots, outcomes)
    panel = step64.add_sr_features(panel, pivots)
    panel = step64.add_temporal_features(panel)
    feats = step64.numeric_features(panel)
    raw_X = panel[feats].replace([np.inf, -np.inf], np.nan)
    fill_values = raw_X.median(numeric_only=True)
    X = raw_X.fillna(fill_values).fillna(0.0)
    return step64, panel, X, feats, fill_values, cat, rules


def target_for_engine(panel: pd.DataFrame, cat: pd.DataFrame, spec: EngineSpec) -> np.ndarray:
    tmp = cat.copy()
    tmp["group_key"] = join_key(tmp, group_cols(spec.group_type))
    trad = tmp[tmp["practical_tradable"] & tmp["group_key"].eq(spec.group_key)]
    y = np.zeros(len(panel), dtype=bool)
    pos = pd.Series(np.arange(len(panel)), index=panel.index)
    for r in trad.itertuples(index=False):
        pt = pd.Timestamp(r.pivot_time)
        if pt not in pos.index:
            continue
        base = int(pos.loc[pt])
        for off in [0, 1, 2]:
            idx = base + off
            if idx < len(panel):
                y[idx] = True
    return y


def fit_engine_bundle():
    step64, panel, X, feats, fill_values, cat, rules = build_training_data()
    dev_mask = (panel.index >= DEV_START) & (panel.index <= DEV_END)
    fitted = {}
    for spec in ENGINES:
        labels = [spec.label]
        s1 = step64.stage1_mask(panel, rules, labels)
        y = target_for_engine(panel, cat, spec)
        train_idx = np.where(s1 & dev_mask)[0]
        ytr = y[train_idx].astype(int)
        if ytr.sum() < 10:
            raise SystemExit(f"not enough positives to train {spec.engine_id}: {int(ytr.sum())}")
        model = model_for(spec.model)
        if spec.model == "hgb":
            spw = (len(ytr) - ytr.sum()) / max(ytr.sum(), 1)
            sw = np.where(ytr == 1, spw, 1.0)
            model.fit(X.iloc[train_idx], ytr, sample_weight=sw)
        else:
            model.fit(X.iloc[train_idx], ytr)
        fitted[spec.engine_id] = model
    return fitted, feats, fill_values, step64, rules


def fit_engines():
    fitted, feats, _, _, _ = fit_engine_bundle()
    return fitted, feats


def prepare_live_panel(
    ticks_path: Path,
    events: pd.DataFrame,
    feats: list[str],
    fill_values: pd.Series | None = None,
) -> pd.DataFrame:
    ticks = read_ticks(ticks_path)
    panel = build_broker_panel(ticks)
    panel = add_m5_indicators(panel)
    panel = add_h1_from_m5(panel)
    hist_pivots = pd.read_csv(RESEARCH / "zzlines_pivot_map_enriched.csv", parse_dates=["pivot_time"])
    live_pivots = live_pivots_from_events(events)
    pivots = pd.concat([hist_pivots[["pivot_time", "price", "side", "label"]], live_pivots], ignore_index=True)
    step64 = load_module(RESEARCH / "64_buy_sell_precision_refine.py", "step64_live")
    panel = step64.add_sr_features(panel, pivots)
    panel = step64.add_temporal_features(panel)
    missing = [c for c in feats if c not in panel.columns]
    if missing:
        raise SystemExit(f"live panel is missing required feature columns: {missing[:20]}")
    X = panel[feats].replace([np.inf, -np.inf], np.nan)
    if fill_values is None:
        fill_values = X.median(numeric_only=True)
    X = X.fillna(fill_values).fillna(0.0)
    return X


def merge_score_csv(existing_path: Path, new_rows: pd.DataFrame, out_path: Path) -> pd.DataFrame:
    frames = []
    if existing_path.exists():
        frames.append(pd.read_csv(existing_path))
    frames.append(new_rows)
    out = pd.concat(frames, ignore_index=True)
    out = out.drop_duplicates(["time", "engine_id"], keep="last").sort_values(["time", "engine_id"])
    out.to_csv(out_path, index=False, float_format="%.6f")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticks", type=Path, required=True, help="Common Files broker tick export CSV")
    ap.add_argument("--events", type=Path, default=COMMON / "VECTOR80_events.csv")
    ap.add_argument("--existing", type=Path, default=RESEARCH / "VECTOR80_model_scores.csv")
    ap.add_argument("--out", type=Path, default=COMMON / "VECTOR80_model_scores.csv")
    ap.add_argument("--research-out", type=Path, default=RESEARCH / "VECTOR80_model_scores.csv")
    ap.add_argument("--day", default=None, help="Optional YYYY-MM-DD filter, e.g. 2026-06-04")
    ap.add_argument("--score-shift-min", type=int, default=180, help="EA adds this shift when matching CSV rows")
    args = ap.parse_args()

    events = load_event_candidates(args.events, args.day)
    if events.empty:
        raise SystemExit("no missing-score VECTOR80 candidates found in events log")
    print(f"candidate rows from events: {len(events)}")

    fitted, feats, fill_values, _, _ = fit_engine_bundle()
    live_X = prepare_live_panel(args.ticks, events, feats, fill_values)

    rows = []
    missing_feature_times = []
    for r in events.itertuples(index=False):
        bar_time = pd.Timestamp(r.bar_time)
        if bar_time not in live_X.index:
            missing_feature_times.append(str(bar_time))
            continue
        engine_id = str(r.engine_id)
        score = float(fitted[engine_id].predict_proba(live_X.loc[[bar_time]])[0, 1])
        csv_time = bar_time - pd.Timedelta(minutes=args.score_shift_min)
        rows.append({"time": csv_time.strftime("%Y-%m-%d %H:%M:%S"), "engine_id": engine_id, "score": score})

    if missing_feature_times:
        sample = ", ".join(missing_feature_times[:10])
        raise SystemExit(f"missing feature rows for {len(missing_feature_times)} candidate times, sample: {sample}")
    if not rows:
        raise SystemExit("no score rows generated")

    new_rows = pd.DataFrame(rows).drop_duplicates(["time", "engine_id"], keep="last")
    combined = merge_score_csv(args.existing, new_rows, args.research_out)
    combined.to_csv(args.out, index=False, float_format="%.6f")

    passed = 0
    for r in new_rows.itertuples(index=False):
        spec = ENGINE_BY_ID[str(r.engine_id)]
        if float(r.score) >= spec.threshold:
            passed += 1
    print(f"generated new score rows: {len(new_rows)}")
    print(f"new rows at/above engine threshold: {passed}")
    print(f"research score CSV: {args.research_out}")
    print(f"MT5 Common score CSV: {args.out}")


if __name__ == "__main__":
    main()
