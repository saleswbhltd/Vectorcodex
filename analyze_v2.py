"""
VECTOR002 trade log analyzer.

Usage:
    python3 analyze_v2.py [trades_csv_path]

If no path given, uses the latest VECTOR002_trades_*.csv in MT5 Common/Files.
Produces a summary mirroring the VECTOR001 analyses.
"""

import sys, glob, os
import pandas as pd
import numpy as np

COMMON = "/mnt/c/Users/cmake/AppData/Roaming/MetaQuotes/Terminal/Common/Files"

def find_latest():
    files = sorted(glob.glob(f"{COMMON}/VECTOR002_trades_*.csv"))
    if files: return files[-1]
    fixed = f"{COMMON}/VECTOR002_trades.csv"
    return fixed if os.path.exists(fixed) else None

def read_csv(path):
    """The EA writes UTF-16 LE (FILE_UNICODE flag) with | separator."""
    return pd.read_csv(path, sep="|", encoding="utf-16")

def main():
    path = sys.argv[1] if len(sys.argv) > 1 else find_latest()
    if not path or not os.path.exists(path):
        print(f"No trades file. Looked in: {COMMON}")
        return
    df = read_csv(path)
    print(f"File: {path}")
    print(f"Rows: {len(df)}")
    if len(df) == 0:
        print("Empty.")
        return

    # Basic numeric coercions
    for col in ["pips","usd","lots","max_favorable_pips","trail_moves",
                "hold_minutes","atr_at_pivot","d2low_at_pivot",
                "confirm_lag_m5","m1_bars_to_trigger",
                "entry_price","initial_sl","close_price","pivot_price"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    print("\n══════════════════════════════════════════════════")
    print("Headline")
    print("══════════════════════════════════════════════════")
    n = len(df)
    wins = (df["pips"] > 0).sum()
    print(f"  Trades        : {n}")
    print(f"  Wins          : {wins} ({100*wins/n:.1f}%)")
    print(f"  Total pips    : {df['pips'].sum():+.1f}")
    print(f"  Avg pips/trade: {df['pips'].mean():+.2f}")
    if df["usd"].notna().any():
        print(f"  Total USD     : ${df['usd'].sum():+.2f}")
    print(f"  Avg MFE       : {df['max_favorable_pips'].mean():.1f}")
    print(f"  Avg hold (min): {df['hold_minutes'].mean():.0f}")

    # Close reason mix
    print("\nClose reasons:")
    for r, cnt in df["close_reason"].value_counts().items():
        sub = df[df["close_reason"] == r]
        print(f"  {r:12s}: n={cnt:4d}  avg pips={sub['pips'].mean():+5.2f}  "
              f"total={sub['pips'].sum():+6.1f}")

    # Per direction
    print("\nPer direction:")
    for d in ("BUY", "SELL"):
        sub = df[df["direction"] == d]
        if len(sub) == 0: continue
        w = (sub["pips"] > 0).sum()
        print(f"  {d}: n={len(sub):3d}  wr={100*w/len(sub):.0f}%  "
              f"avg pips={sub['pips'].mean():+5.2f}  total={sub['pips'].sum():+6.1f}")

    # Per month
    print("\nPer month:")
    df["close_dt"] = pd.to_datetime(df["close_time"], format="%Y.%m.%d %H:%M:%S",
                                    errors="coerce")
    df["month"] = df["close_dt"].dt.to_period("M").astype(str)
    by_m = df.groupby("month").agg(n=("pips","size"),
                                    wins=("pips", lambda x: (x>0).sum()),
                                    avg=("pips","mean"),
                                    total=("pips","sum")).round(2)
    by_m["wr%"] = (100*by_m["wins"]/by_m["n"]).round(0)
    print(by_m[["n","wins","wr%","avg","total"]].to_string())

    # Filter context — what pivots got picked?
    print("\nFilter context distributions (entries only):")
    for col in ["atr_at_pivot","d2low_at_pivot","confirm_lag_m5",
                "m1_bars_to_trigger","trail_moves"]:
        if col in df.columns:
            s = df[col].dropna()
            if len(s)==0: continue
            print(f"  {col:25s} mean={s.mean():6.2f}  median={s.median():6.2f}  "
                  f"p25={s.quantile(.25):6.2f}  p75={s.quantile(.75):6.2f}")

    # Top wins / losses
    print("\nTop 5 wins:")
    print(df.nlargest(5,"pips")[["entry_time","direction","entry_price",
                                   "close_price","close_reason","pips","max_favorable_pips"]]
          .to_string(index=False))
    print("\nTop 5 losses:")
    print(df.nsmallest(5,"pips")[["entry_time","direction","entry_price",
                                    "close_price","close_reason","pips","max_favorable_pips"]]
          .to_string(index=False))

if __name__ == "__main__":
    main()
