"""
Step 47 — Compare broker MT5 tick history against Dukascopy tick history.

Workflow:
  1. Run VECTOR_BrokerTickExport.mq5 in MT5 for 3-4 months.
  2. Run this script with the exported Common/Files CSV path.

The script:
  - resamples broker ticks to M5 using mid price
  - resamples Dukascopy ticks to the same overlapping period
  - compares M5 OHLC/tick counts
  - builds 20-pip ZZ pivots from each source and compares one-to-one

Example:
  python3 47_compare_broker_ticks.py \
    /mnt/c/Users/cmake/AppData/Roaming/MetaQuotes/Terminal/Common/Files/BROKER_TICKS_EURUSD_20250201_20250601.csv \
    --broker-time-shift-hours -3
"""

import argparse
import os
import pandas as pd
import numpy as np

DUKA_TICKS = "/home/cmake/Vector/research/EURUSD_TICK_dukascopy_2025_2026.csv.gz"
OUT_DIR = "/home/cmake/Vector/research"
PIP = 0.0001


def load_broker_ticks(path):
    df = pd.read_csv(path)
    if "time_msc" in df.columns:
        df["datetime"] = pd.to_datetime(df["time_msc"], unit="ms", utc=True).dt.tz_localize(None)
    else:
        df["datetime"] = pd.to_datetime(df["datetime"], utc=True, format="mixed").dt.tz_localize(None)
    for c in ["bid", "ask", "last", "mid"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    if "mid" not in df.columns or df["mid"].isna().all():
        df["mid"] = np.where(
            (df["bid"] > 0) & (df["ask"] > 0),
            (df["bid"] + df["ask"]) * 0.5,
            np.where(df.get("last", 0) > 0, df.get("last", 0), df["bid"].fillna(df["ask"]))
        )
    df = df.dropna(subset=["datetime", "mid"]).sort_values("datetime")
    return df[["datetime", "mid", "bid", "ask"]].drop_duplicates("datetime")


def load_duka_ticks(start, end):
    df = pd.read_csv(DUKA_TICKS, parse_dates=["datetime"])
    df["datetime"] = pd.to_datetime(df["datetime"], utc=True, format="ISO8601").dt.tz_localize(None)
    df = df[(df["datetime"] >= start) & (df["datetime"] <= end)].copy()
    if "mid" not in df.columns:
        df["mid"] = (df["bid"] + df["ask"]) * 0.5
    return df[["datetime", "mid", "bid", "ask"]].drop_duplicates("datetime").sort_values("datetime")


def resample_m5(ticks):
    x = ticks.set_index("datetime").sort_index()
    ohlc = x["mid"].resample("5min", label="left", closed="left").ohlc()
    count = x["mid"].resample("5min", label="left", closed="left").count()
    spread = ((x["ask"] - x["bid"]) / PIP).resample("5min", label="left", closed="left").mean()
    out = ohlc.join(count.rename("tick_count")).join(spread.rename("spread_avg_pips"))
    out = out.dropna(subset=["open"])
    return out


def detect_zz(df, thresh_pips):
    thresh = thresh_pips * PIP
    h = df["high"].values
    l = df["low"].values
    t = df.index.values
    if len(df) < 3:
        return pd.DataFrame(columns=["pivot_time", "confirm_time", "price", "label"])
    up = h[1] >= h[0]
    ext = h[1] if up else l[1]
    ext_i = 1
    prev_h = None
    prev_l = None
    out = []
    for i in range(2, len(df)):
        if up:
            if h[i] > ext:
                ext, ext_i = h[i], i
            elif l[i] <= ext - thresh:
                label = "H0" if prev_h is None else ("HH" if ext > prev_h else "LH")
                out.append((pd.Timestamp(t[ext_i]), pd.Timestamp(t[i]), round(float(ext), 5), label))
                prev_h = ext
                up = False
                ext, ext_i = l[i], i
        else:
            if l[i] < ext:
                ext, ext_i = l[i], i
            elif h[i] >= ext + thresh:
                label = "L0" if prev_l is None else ("HL" if ext > prev_l else "LL")
                out.append((pd.Timestamp(t[ext_i]), pd.Timestamp(t[i]), round(float(ext), 5), label))
                prev_l = ext
                up = True
                ext, ext_i = h[i], i
    return (
        pd.DataFrame(out, columns=["pivot_time", "confirm_time", "price", "label"])
        .query("label in ['HH','HL','LH','LL']")
        .reset_index(drop=True)
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("broker_tick_csv")
    ap.add_argument("--threshold", type=float, default=20.0)
    ap.add_argument("--broker-time-shift-hours", type=float, default=0.0,
                    help="Shift broker tick timestamps before resampling. Use negative values when broker server time is ahead of UTC.")
    args = ap.parse_args()

    print("loading broker ticks...")
    broker_ticks = load_broker_ticks(args.broker_tick_csv)
    if args.broker_time_shift_hours != 0:
        broker_ticks["datetime"] = broker_ticks["datetime"] + pd.Timedelta(hours=args.broker_time_shift_hours)
    start = broker_ticks["datetime"].min()
    end = broker_ticks["datetime"].max()
    print(f"  broker ticks: {len(broker_ticks):,}  {start} -> {end}")

    print("loading Dukascopy ticks for overlap...")
    duka_ticks = load_duka_ticks(start, end)
    print(f"  duka ticks:   {len(duka_ticks):,}  {duka_ticks['datetime'].min()} -> {duka_ticks['datetime'].max()}")

    broker_m5 = resample_m5(broker_ticks)
    duka_m5 = resample_m5(duka_ticks)
    common_idx = broker_m5.index.intersection(duka_m5.index)
    broker_m5 = broker_m5.loc[common_idx]
    duka_m5 = duka_m5.loc[common_idx]
    print(f"\ncommon M5 bars: {len(common_idx):,}")

    diffs = {}
    for c in ["open", "high", "low", "close"]:
        diffs[c + "_mean_abs_pips"] = float(((broker_m5[c] - duka_m5[c]).abs() / PIP).mean())
        diffs[c + "_max_abs_pips"] = float(((broker_m5[c] - duka_m5[c]).abs() / PIP).max())
    print("\nM5 OHLC absolute differences in pips:")
    for k, v in diffs.items():
        print(f"  {k}: {v:.2f}")
    print(f"  broker avg ticks/bar: {broker_m5['tick_count'].mean():.1f}")
    print(f"  duka avg ticks/bar:   {duka_m5['tick_count'].mean():.1f}")

    broker_p = detect_zz(broker_m5, args.threshold)
    duka_p = detect_zz(duka_m5, args.threshold)
    cols = ["pivot_time", "confirm_time", "price", "label"]
    cmp = broker_p[cols].merge(duka_p[cols], on=cols, how="outer", indicator=True)

    shift_tag = "" if args.broker_time_shift_hours == 0 else f"_shift{args.broker_time_shift_hours:+g}h"
    stem = os.path.splitext(os.path.basename(args.broker_tick_csv))[0] + shift_tag
    out_b = f"{OUT_DIR}/{stem}_broker_m5.csv"
    out_d = f"{OUT_DIR}/{stem}_duka_overlap_m5.csv"
    out_c = f"{OUT_DIR}/{stem}_pivot_compare.csv"
    broker_m5.to_csv(out_b, float_format="%.6f")
    duka_m5.to_csv(out_d, float_format="%.6f")
    cmp.to_csv(out_c, index=False)

    print(f"\nZZ {args.threshold:g}-pip pivots over overlap:")
    print(f"  broker: {len(broker_p)} {broker_p['label'].value_counts().reindex(['HH','HL','LH','LL']).fillna(0).astype(int).to_dict()}")
    print(f"  duka:   {len(duka_p)} {duka_p['label'].value_counts().reindex(['HH','HL','LH','LL']).fillna(0).astype(int).to_dict()}")
    print(f"  exact matches: {(cmp['_merge'] == 'both').sum()}")
    print(f"  broker only:   {(cmp['_merge'] == 'left_only').sum()}")
    print(f"  duka only:     {(cmp['_merge'] == 'right_only').sum()}")
    print("\nSaved:")
    print(f"  {out_b}")
    print(f"  {out_d}")
    print(f"  {out_c}")


if __name__ == "__main__":
    main()
