"""
Step 46 — Compare research pivot map against MT5-exported M5 bars for one month.

Default comparison:
  month: 2025-03
  ZZ:    20-pip threshold

The MT5 file is expected from Scripts/ExportM5Bars.mq5:
  /mnt/c/Users/cmake/AppData/Roaming/MetaQuotes/Terminal/Common/Files/EURUSD_M5_bars.csv

Outputs:
  compare_mt5_YYYY-MM.csv
"""

import argparse
import pandas as pd

PIP = 0.0001
MT5 = "/mnt/c/Users/cmake/AppData/Roaming/MetaQuotes/Terminal/Common/Files/EURUSD_M5_bars.csv"
PANEL = "/home/cmake/Vector/research/EURUSD_M5_FULL_PANEL.csv.gz"


def detect(df, thresh_pips):
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
    ap.add_argument("--month", default="2025-03", help="YYYY-MM")
    ap.add_argument("--threshold", type=float, default=20.0)
    args = ap.parse_args()

    month_start = pd.Timestamp(args.month + "-01")
    month_end = month_start + pd.offsets.MonthBegin(1)

    mt5 = pd.read_csv(MT5)
    mt5["datetime"] = pd.to_datetime(mt5["datetime"], format="%Y.%m.%d %H:%M")
    mt5 = mt5.set_index("datetime").sort_index()

    panel = pd.read_csv(PANEL, index_col=0, parse_dates=True)
    common_start = max(mt5.index.min(), panel.index.min())
    common_end = min(mt5.index.max(), panel.index.max())
    mt5 = mt5.loc[common_start:common_end]
    panel = panel.loc[common_start:common_end]

    mt5_month_bars = mt5.loc[month_start:month_end - pd.Timedelta(minutes=5)]
    panel_month_bars = panel.loc[month_start:month_end - pd.Timedelta(minutes=5)]

    mt5_p = detect(mt5, args.threshold)
    panel_p = detect(panel, args.threshold)
    mt5_m = mt5_p[(mt5_p["pivot_time"] >= month_start) & (mt5_p["pivot_time"] < month_end)].copy()
    panel_m = panel_p[(panel_p["pivot_time"] >= month_start) & (panel_p["pivot_time"] < month_end)].copy()

    cols = ["pivot_time", "confirm_time", "price", "label"]
    cmp = mt5_m[cols].merge(panel_m[cols], on=cols, how="outer", indicator=True)
    out = f"/home/cmake/Vector/research/compare_mt5_{args.month}.csv"
    cmp.to_csv(out, index=False)

    print(f"Month: {args.month}  threshold={args.threshold:g} pip")
    print(f"Common range: {common_start} -> {common_end}")
    print(f"MT5 month bars:   {len(mt5_month_bars)}")
    print(f"Panel month bars: {len(panel_month_bars)}")
    print()
    print(f"MT5 pivots:   {len(mt5_m)} {mt5_m['label'].value_counts().reindex(['HH','HL','LH','LL']).fillna(0).astype(int).to_dict()}")
    print(f"Panel pivots: {len(panel_m)} {panel_m['label'].value_counts().reindex(['HH','HL','LH','LL']).fillna(0).astype(int).to_dict()}")
    print(f"Exact matches: {(cmp['_merge'] == 'both').sum()}")
    print(f"MT5 only:      {(cmp['_merge'] == 'left_only').sum()}")
    print(f"Panel only:    {(cmp['_merge'] == 'right_only').sum()}")
    print(f"Saved: {out}")


if __name__ == "__main__":
    main()

