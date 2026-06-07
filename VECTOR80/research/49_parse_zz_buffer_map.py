"""
Step 49 - Parse ZigZag Lines MTF buffer dump into pivot rows.

Input is produced by VECTOR_ZZBufferPivotExport.mq5.

The Market indicator exposes the active ZigZag tip as:
  b0 = tip price
  b1 = tip time as Unix timestamp
  b4 = leg direction (+1 forming HIGH, -1 forming LOW)

Buffers 5/6 are support/resistance levels on recent bars in this export, not
sparse pivot buffers, so this parser builds the map from b0/b1/b4 and compares
it against the TKTL/ZZLEG depth-window OHLC map from the same raw bars.
"""

from __future__ import annotations

import argparse
import os

import numpy as np
import pandas as pd

from importlib.machinery import SourceFileLoader


OUT_DIR = "/home/cmake/Vector/research"
DEFAULT_RAW = (
    "/mnt/c/Users/cmake/AppData/Roaming/MetaQuotes/Terminal/Common/Files/"
    "VECTOR_ZZBUF_EURUSD_PERIOD_M5_D12_Dev5_Back3_Tmp1000_raw.csv"
)

tktl = SourceFileLoader("tktl_depth", f"{OUT_DIR}/48_tktl_depth_pivot_compare.py").load_module()


def load_raw(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["datetime"] = pd.to_datetime(df["time"], format="%Y.%m.%d %H:%M:%S")
    for c in ["open", "high", "low", "close"] + [f"b{i}" for i in range(10)]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    for c in [f"b{i}" for i in range(10)]:
        df.loc[df[c].abs() > 1e10, c] = np.nan
    return df.sort_values("datetime").reset_index(drop=True)


def extract_indicator_pivots(raw: pd.DataFrame) -> pd.DataFrame:
    ref = float(raw["close"].dropna().iloc[-1])
    x = raw[
        raw["b1"].between(1500000000, 2100000000)
        & raw["b0"].between(ref * 0.8, ref * 1.2)
        & raw["b4"].isin([-1.0, 1.0])
    ].copy()
    if x.empty:
        return pd.DataFrame(columns=["pivot_time", "price", "side", "source_bar_time", "b4"])

    x["pivot_time"] = pd.to_datetime(x["b1"], unit="s")
    x["price"] = x["b0"].round(5)
    x["side"] = np.where(x["b4"] > 0, "HIGH", "LOW")
    x["source_bar_time"] = x["datetime"]

    # Keep the last observation for each pivot key. With a complete export this
    # removes repeated bar references while preserving the final known tip.
    x = x.sort_values("source_bar_time").drop_duplicates(["pivot_time", "side", "price"], keep="last")
    x = x.sort_values("pivot_time").reset_index(drop=True)

    prev_high = None
    prev_low = None
    labels = []
    for r in x.itertuples(index=False):
        if r.side == "HIGH":
            label = "H0" if prev_high is None else ("HH" if r.price > prev_high else "LH")
            prev_high = r.price
        else:
            label = "L0" if prev_low is None else ("HL" if r.price > prev_low else "LL")
            prev_low = r.price
        labels.append(label)
    x["label"] = labels
    return x[["pivot_time", "price", "side", "label", "source_bar_time", "b4"]]


def raw_to_m5(raw: pd.DataFrame) -> pd.DataFrame:
    cols = ["datetime", "open", "high", "low", "close"]
    return raw[cols].dropna().drop_duplicates("datetime").set_index("datetime").sort_index()


def compare(ind: pd.DataFrame, ohlc: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    cols = ["pivot_time", "price", "side", "label"]
    exact = ind[cols].merge(ohlc[cols], on=cols, how="outer", indicator=True)
    tol = tktl.nearest_time_stats(ind, ohlc, [0, 5, 10, 15, 30, 60])
    return exact, tol


def counts(df: pd.DataFrame) -> dict[str, int]:
    if df.empty:
        return {}
    return df["label"].value_counts().reindex(["H0", "HH", "LH", "L0", "HL", "LL"]).fillna(0).astype(int).to_dict()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default=DEFAULT_RAW)
    ap.add_argument("--depth", type=int, default=12)
    args = ap.parse_args()

    raw = load_raw(args.raw)
    ind = extract_indicator_pivots(raw)
    m5 = raw_to_m5(raw)
    ohlc = tktl.detect_tktl_depth_pivots(m5, args.depth)
    exact, tol = compare(ind, ohlc)

    stem = os.path.splitext(os.path.basename(args.raw))[0].replace("_raw", "")
    out_i = f"{OUT_DIR}/{stem}_indicator_pivots.csv"
    out_o = f"{OUT_DIR}/{stem}_ohlc_depth{args.depth}_pivots.csv"
    out_c = f"{OUT_DIR}/{stem}_indicator_vs_ohlc_compare.csv"
    out_s = f"{OUT_DIR}/{stem}_indicator_vs_ohlc_match_stats.csv"

    ind.to_csv(out_i, index=False)
    ohlc.to_csv(out_o, index=False)
    exact.to_csv(out_c, index=False)
    tol.to_csv(out_s, index=False)

    print(f"raw bars: {len(raw):,}  {raw['datetime'].min()} -> {raw['datetime'].max()}")
    print(f"indicator pivots: {len(ind):,} {counts(ind)}")
    print(f"OHLC depth pivots: {len(ohlc):,} {counts(ohlc)}")
    print(f"exact matches: {int((exact['_merge'] == 'both').sum()):,}")
    print(tol.to_string(index=False, float_format=lambda x: f"{x:.3f}"))
    print("Saved:")
    print(f"  {out_i}")
    print(f"  {out_o}")
    print(f"  {out_c}")
    print(f"  {out_s}")


if __name__ == "__main__":
    main()
