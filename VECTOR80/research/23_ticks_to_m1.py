"""
Step 23 — Aggregate raw tick data into M1 OHLC bars.

The broker M1 export only gave us 100K bars (Feb 23 → Jun 1) but the tick
export goes back to Jan 2. We can synthesise M1 bars from ticks to cover the
missing Jan 2 → Feb 23 period and get a clean 5-month M1 dataset.

We aggregate by minute using the MID price (= (bid + ask) / 2) — the same
price that drives M5/M1 OHLC in MT5.

Input:  EURUSD_ticks.csv (8.8M rows, 393MB)
Output: m1_from_ticks_2026.csv.gz
"""

import pandas as pd
import numpy as np

TICKS = "/mnt/c/Users/cmake/AppData/Roaming/MetaQuotes/Terminal/5FFA568149E88FCD5B44D926DCFEAA79/MQL5/Files/EURUSD_ticks.csv"
OUT   = "/home/cmake/Vector/research/m1_from_ticks_2026.csv.gz"

CHUNKSIZE = 500_000  # rows per chunk

print("aggregating ticks → M1 bars (chunked)...")
all_minutes = {}     # minute_ts → {open, high, low, close, vol}

chunks_read = 0
ticks_read  = 0
for chunk in pd.read_csv(TICKS, chunksize=CHUNKSIZE):
    chunks_read += 1
    ticks_read  += len(chunk)
    # Use mid price; if last == 0 fall back to (bid+ask)/2
    chunk["mid"] = (chunk["bid"] + chunk["ask"]) / 2
    chunk = chunk[chunk["mid"] > 0]
    # Floor timestamp to minute
    chunk["minute"] = (chunk["time_msc"] // 60000) * 60000

    g = chunk.groupby("minute").agg(
        open=("mid", "first"),
        high=("mid", "max"),
        low =("mid", "min"),
        close=("mid", "last"),
        tick_volume=("mid", "size"),
    )
    # Merge into accumulator
    for ts, row in g.iterrows():
        if ts in all_minutes:
            a = all_minutes[ts]
            a["high"] = max(a["high"], row["high"])
            a["low"]  = min(a["low"],  row["low"])
            a["close"] = row["close"]
            a["tick_volume"] += row["tick_volume"]
        else:
            all_minutes[ts] = {"open": row["open"], "high": row["high"],
                               "low": row["low"], "close": row["close"],
                               "tick_volume": row["tick_volume"]}
    if chunks_read % 2 == 0:
        print(f"  chunk {chunks_read:>2d}: {ticks_read:>9,} ticks read, "
              f"{len(all_minutes):>6,} unique minutes")

print(f"\nTotal ticks: {ticks_read:,}")
print(f"Unique minutes: {len(all_minutes):,}")

# Convert to DataFrame
df = pd.DataFrame.from_dict(all_minutes, orient="index").sort_index()
df.index = pd.to_datetime(df.index, unit="ms")
df.index.name = "datetime"
print(f"DataFrame: {len(df):,} M1 bars  "
      f"({df.index[0]} → {df.index[-1]})")

# Sanity: check for missing minutes within trading hours
df.to_csv(OUT, compression="gzip", float_format="%.6f")
print(f"saved → {OUT}")
