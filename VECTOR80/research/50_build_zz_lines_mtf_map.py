"""
Step 50 - Build a Python map for ZigZag Lines MTF settings.

This reproduces the MetaQuotes Examples\\ZigZag algorithm used by many MT5
ZigZag-family indicators:

  Depth=12, Deviation=5 points, Backstep=3

The Market indicator "ZigZag Lines MTF for MT5" exposes only a limited set of
recent buffer pivots, so this script builds the equivalent map over the full
available M5 history in Python. Broker indicator timestamps are server time;
comparisons to Dukascopy use a -3h shift.
"""

from __future__ import annotations

import argparse
import os

import numpy as np
import pandas as pd


OUT_DIR = "/home/cmake/Vector/research"
DUKA_M5 = f"{OUT_DIR}/EURUSD_M5_dukascopy_2025_2026.csv.gz"
BROKER_RAW = (
    "/mnt/c/Users/cmake/AppData/Roaming/MetaQuotes/Terminal/Common/Files/"
    "VECTOR_ZZBUF_EURUSD_PERIOD_M5_D12_Dev5_Back3_Tmp20000_raw.csv"
)
INDICATOR_PIVOTS = f"{OUT_DIR}/VECTOR_ZZBUF_EURUSD_PERIOD_M5_D12_Dev5_Back3_Tmp20000_indicator_pivots.csv"
POINT = 0.00001


def load_m5(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    if "datetime" not in df.columns:
        if "time" in df.columns:
            df = df.rename(columns={"time": "datetime"})
        else:
            df = df.rename(columns={df.columns[0]: "datetime"})
    df["datetime"] = pd.to_datetime(df["datetime"], utc=True, format="mixed").dt.tz_localize(None)
    for c in ["open", "high", "low", "close"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.dropna(subset=["datetime", "high", "low"]).drop_duplicates("datetime").sort_values("datetime").reset_index(drop=True)


def highest(values: np.ndarray, depth: int, start: int) -> int:
    if start < 0:
        return 0
    max_val = values[start]
    index = start
    i = start - 1
    while i > start - depth and i >= 0:
        if values[i] > max_val:
            index = i
            max_val = values[i]
        i -= 1
    return index


def lowest(values: np.ndarray, depth: int, start: int) -> int:
    if start < 0:
        return 0
    min_val = values[start]
    index = start
    i = start - 1
    while i > start - depth and i >= 0:
        if values[i] < min_val:
            index = i
            min_val = values[i]
        i -= 1
    return index


def detect_metaquotes_zigzag(
    m5: pd.DataFrame,
    depth: int = 12,
    deviation: int = 5,
    backstep: int = 3,
    point: float = POINT,
) -> pd.DataFrame:
    """Port of MQL5 Indicators/Examples/ZigZag.mq5 full initial calculation."""
    high = m5["high"].to_numpy(dtype=float)
    low = m5["low"].to_numpy(dtype=float)
    n = len(m5)
    zigzag = np.zeros(n, dtype=float)
    high_map = np.zeros(n, dtype=float)
    low_map = np.zeros(n, dtype=float)

    if n < 100:
        return empty_frame()

    last_low = 0.0
    last_high = 0.0
    start = depth

    for shift in range(start, n):
        val = low[lowest(low, depth, shift)]
        if val == last_low:
            val = 0.0
        else:
            last_low = val
            if (low[shift] - val) > deviation * point:
                val = 0.0
            else:
                for back in range(1, backstep + 1):
                    res = low_map[shift - back]
                    if res != 0 and res > val:
                        low_map[shift - back] = 0.0
        low_map[shift] = val if low[shift] == val else 0.0

        val = high[highest(high, depth, shift)]
        if val == last_high:
            val = 0.0
        else:
            last_high = val
            if (val - high[shift]) > deviation * point:
                val = 0.0
            else:
                for back in range(1, backstep + 1):
                    res = high_map[shift - back]
                    if res != 0 and res < val:
                        high_map[shift - back] = 0.0
        high_map[shift] = val if high[shift] == val else 0.0

    last_low = 0.0
    last_high = 0.0
    last_low_pos = 0
    last_high_pos = 0
    # 0=Extremum, 1=Peak, -1=Bottom
    extreme_search = 0

    for shift in range(start, n):
        if extreme_search == 0:
            if last_low == 0.0 and last_high == 0.0:
                if high_map[shift] != 0.0:
                    last_high = high[shift]
                    last_high_pos = shift
                    extreme_search = -1
                    zigzag[shift] = last_high
                if low_map[shift] != 0.0:
                    last_low = low[shift]
                    last_low_pos = shift
                    extreme_search = 1
                    zigzag[shift] = last_low
        elif extreme_search == 1:
            if low_map[shift] != 0.0 and low_map[shift] < last_low and high_map[shift] == 0.0:
                zigzag[last_low_pos] = 0.0
                last_low_pos = shift
                last_low = low_map[shift]
                zigzag[shift] = last_low
            if high_map[shift] != 0.0 and low_map[shift] == 0.0:
                last_high = high_map[shift]
                last_high_pos = shift
                zigzag[shift] = last_high
                extreme_search = -1
        elif extreme_search == -1:
            if high_map[shift] != 0.0 and high_map[shift] > last_high and low_map[shift] == 0.0:
                zigzag[last_high_pos] = 0.0
                last_high_pos = shift
                last_high = high_map[shift]
                zigzag[shift] = last_high
            if low_map[shift] != 0.0 and high_map[shift] == 0.0:
                last_low = low_map[shift]
                last_low_pos = shift
                zigzag[shift] = last_low
                extreme_search = 1

    rows = []
    times = pd.to_datetime(m5["datetime"])
    for i, price in enumerate(zigzag):
        if price == 0.0:
            continue
        side = "HIGH" if high_map[i] != 0.0 and abs(price - high[i]) < 1e-10 else "LOW"
        rows.append({"pivot_time": times.iloc[i], "bar_index": i, "price": round(float(price), 5), "side": side})

    out = pd.DataFrame(rows)
    return add_labels(out)


def empty_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=["pivot_time", "bar_index", "price", "side", "label"])


def add_labels(pivots: pd.DataFrame) -> pd.DataFrame:
    if pivots.empty:
        return empty_frame()
    prev_high = None
    prev_low = None
    labels = []
    for r in pivots.itertuples(index=False):
        if r.side == "HIGH":
            label = "H0" if prev_high is None else ("HH" if r.price > prev_high else "LH")
            prev_high = r.price
        else:
            label = "L0" if prev_low is None else ("HL" if r.price > prev_low else "LL")
            prev_low = r.price
        labels.append(label)
    out = pivots.copy()
    out["label"] = labels
    return out


def counts(df: pd.DataFrame) -> dict[str, int]:
    return df["label"].value_counts().reindex(["H0", "HH", "LH", "L0", "HL", "LL"]).fillna(0).astype(int).to_dict()


def nearest_match_stats(a: pd.DataFrame, b: pd.DataFrame, tolerances: list[int]) -> pd.DataFrame:
    rows = []
    for mode in ["side", "side+label"]:
        for tol in tolerances:
            used_b = set()
            matches = 0
            for _, r in a.iterrows():
                cand = b[b["side"].eq(r["side"])].copy()
                if mode == "side+label":
                    cand = cand[cand["label"].eq(r["label"])]
                if cand.empty:
                    continue
                dt = (cand["pivot_time"] - r["pivot_time"]).abs()
                cand = cand.loc[dt <= pd.Timedelta(minutes=tol)].copy()
                if cand.empty:
                    continue
                cand["_dt"] = dt.loc[cand.index]
                cand["_price_pips"] = (cand["price"] - r["price"]).abs() / 0.0001
                bi = int(cand.sort_values(["_dt", "_price_pips"]).index[0])
                if bi in used_b:
                    continue
                used_b.add(bi)
                matches += 1
            rows.append(
                {
                    "mode": mode,
                    "tolerance_minutes": tol,
                    "matches": matches,
                    "a_recall": matches / len(a) if len(a) else 0,
                    "b_recall": len(used_b) / len(b) if len(b) else 0,
                }
            )
    return pd.DataFrame(rows)


def validate_against_indicator(depth: int, deviation: int, backstep: int) -> None:
    if not os.path.exists(BROKER_RAW) or not os.path.exists(INDICATOR_PIVOTS):
        return
    broker = load_m5(BROKER_RAW)
    py = detect_metaquotes_zigzag(broker, depth, deviation, backstep)
    ind = pd.read_csv(INDICATOR_PIVOTS, parse_dates=["pivot_time"])
    start, end = ind["pivot_time"].min(), ind["pivot_time"].max()
    py = py[(py["pivot_time"] >= start - pd.Timedelta(hours=2)) & (py["pivot_time"] <= end + pd.Timedelta(hours=2))].reset_index(drop=True)
    exact = ind[["pivot_time", "price", "side", "label"]].merge(
        py[["pivot_time", "price", "side", "label"]],
        on=["pivot_time", "price", "side", "label"],
        how="outer",
        indicator=True,
    )
    stats = nearest_match_stats(ind, py, [0, 5, 15, 30, 60])
    print("\nValidation vs exported broker indicator pivots:")
    print(f"  indicator: {len(ind)} {counts(ind)}")
    print(f"  python window: {len(py)} {counts(py)}")
    print(f"  exact time+price+side+label: {int((exact['_merge'] == 'both').sum())}")
    print(stats.to_string(index=False, float_format=lambda x: f"{x:.3f}"))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--m5", default=DUKA_M5)
    ap.add_argument("--depth", type=int, default=12)
    ap.add_argument("--deviation", type=int, default=5)
    ap.add_argument("--backstep", type=int, default=3)
    ap.add_argument("--start", default=None)
    ap.add_argument("--end", default=None)
    ap.add_argument("--tag", default="EURUSD_M5_ZZLINES_D12_Dev5_Back3")
    ap.add_argument("--validate", action="store_true")
    args = ap.parse_args()

    m5 = load_m5(args.m5)
    if args.start:
        m5 = m5[m5["datetime"] >= pd.Timestamp(args.start)]
    if args.end:
        m5 = m5[m5["datetime"] <= pd.Timestamp(args.end)]
    m5 = m5.reset_index(drop=True)

    pivots = detect_metaquotes_zigzag(m5, args.depth, args.deviation, args.backstep)

    stem = f"{OUT_DIR}/{args.tag}"
    if args.start or args.end:
        s = args.start or str(m5["datetime"].min()).replace(" ", "_")
        e = args.end or str(m5["datetime"].max()).replace(" ", "_")
        stem += f"_{s}_to_{e}"
    out = stem + "_pivot_map.csv"
    pivots.to_csv(out, index=False)

    print(f"bars: {len(m5):,}  {m5['datetime'].min()} -> {m5['datetime'].max()}")
    print(f"pivots: {len(pivots):,} {counts(pivots)}")
    print(f"saved: {out}")

    if args.validate:
        validate_against_indicator(args.depth, args.deviation, args.backstep)


if __name__ == "__main__":
    main()
