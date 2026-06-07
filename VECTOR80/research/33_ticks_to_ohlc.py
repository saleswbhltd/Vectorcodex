"""
Step 33 — Concatenate the 3 tick chunks and resample to M1/M5 OHLC.

Once Dukascopy downloads complete, the EURUSD/ folder has 3 tick CSVs
(2025 H1, 2025 H2, 2026 H1). This concatenates them and produces:
  EURUSD_M5_dukascopy_2025_2026.csv.gz
  EURUSD_M1_dukascopy_2025_2026.csv.gz
  EURUSD_TICK_dukascopy_2025_2026.csv.gz    (sorted, deduped, compressed)
"""

import pandas as pd
import numpy as np
import glob, os

SRC_DIR = "/mnt/c/Users/cmake/Documents/MarketData/EURUSD"
OUT_DIR = "/home/cmake/Vector/research"


def load_chunks():
    files = sorted(glob.glob(f"{SRC_DIR}/EURUSD_TICK_2025*.csv") +
                    glob.glob(f"{SRC_DIR}/EURUSD_TICK_2026*.csv"))
    if not files:
        print("No tick chunks found")
        return None
    print(f"Loading {len(files)} chunks:")
    frames = []
    for f in files:
        sz = os.path.getsize(f) / 1024 / 1024
        print(f"  {os.path.basename(f)} ({sz:.0f} MB)")
        df = pd.read_csv(f)
        df["datetime"] = pd.to_datetime(df["datetime"], utc=True, format="ISO8601")
        frames.append(df)
    return frames


def main():
    frames = load_chunks()
    if frames is None: return
    print("\nConcatenating...")
    df = pd.concat(frames, ignore_index=True)
    df = df.sort_values("datetime").drop_duplicates("datetime").reset_index(drop=True)
    print(f"  total ticks: {len(df):,}")
    print(f"  range: {df['datetime'].iloc[0]} → {df['datetime'].iloc[-1]}")

    # Save consolidated tick file (compressed)
    df["mid"] = (df["bid"] + df["ask"]) / 2
    consolidated = f"{OUT_DIR}/EURUSD_TICK_dukascopy_2025_2026.csv.gz"
    df.to_csv(consolidated, index=False, compression="gzip", float_format="%.5f")
    print(f"saved tick file → {consolidated}")

    # Resample to M5 / M1 using MID price
    print("\nResampling to M5/M1...")
    df = df.set_index("datetime")

    for tf, rule in [("M5", "5min"), ("M1", "1min")]:
        ohlc = df["mid"].resample(rule, label="left", closed="left").ohlc()
        tick_count = df["mid"].resample(rule, label="left", closed="left").count()
        bid_vol_sum = df["bid_vol"].resample(rule, label="left", closed="left").sum()
        ask_vol_sum = df["ask_vol"].resample(rule, label="left", closed="left").sum()
        out = ohlc.join(tick_count.rename("tick_volume")).join(
                       bid_vol_sum.rename("bid_volume")).join(
                       ask_vol_sum.rename("ask_volume"))
        out = out.dropna(subset=["open"])
        out.index.name = "datetime"
        out_path = f"{OUT_DIR}/EURUSD_{tf}_dukascopy_2025_2026.csv.gz"
        out.to_csv(out_path, compression="gzip", float_format="%.6f")
        print(f"  {tf}: {len(out):,} bars  → {out_path}")


if __name__ == "__main__":
    main()
