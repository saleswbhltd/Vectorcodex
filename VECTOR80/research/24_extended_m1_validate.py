"""
Step 24 — Re-validate with EXTENDED M1 history (5 months from ticks).

Uses m1_from_ticks_2026.csv.gz (150K bars, Jan-Jun 2026) instead of the
broker's 100K-bar M1 export (Feb 23 onwards). This gives us January as
additional OOS data, where M5 ATR was in [6,11] for ~24% of pivots — a
distinct regime from March which dominated the earlier sample.
"""

import pandas as pd
import numpy as np

M5_DATA = "/home/cmake/Vector/research/m5_2026_deep.csv.gz"
M1_TICK = "/home/cmake/Vector/research/m1_from_ticks_2026.csv.gz"
PIP = 0.0001
M5_THRESH = 20


def detect(df, t_pips):
    thresh = t_pips * PIP
    h = df["high"].values; l = df["low"].values; t = df.index.values
    up = h[1] >= h[0]; ext = h[1] if up else l[1]; ext_i = 1
    out = []
    for i in range(2, len(df)):
        if up:
            if h[i] > ext: ext, ext_i = h[i], i
            elif l[i] <= ext - thresh:
                out.append((t[ext_i], t[i], ext, True, ext_i, i))
                up=False; ext,ext_i=l[i],i
        else:
            if l[i] < ext: ext, ext_i = l[i], i
            elif h[i] >= ext + thresh:
                out.append((t[ext_i], t[i], ext, False, ext_i, i))
                up=True; ext,ext_i=h[i],i
    return pd.DataFrame(out, columns=["pivot_time","confirm_time","price","is_high","pi","ci"])


def main():
    M5 = pd.read_csv(M5_DATA, index_col=0, parse_dates=True)
    M1 = pd.read_csv(M1_TICK, index_col=0, parse_dates=True)
    print(f"M5: {len(M5):,} bars  ({M5.index[0]} → {M5.index[-1]})")
    print(f"M1: {len(M1):,} bars  ({M1.index[0]} → {M1.index[-1]})")

    piv = detect(M5, M5_THRESH)
    piv["confirm_lag"] = ((piv["confirm_time"] - piv["pivot_time"]).dt.total_seconds()/300).astype(int)
    atr14 = M5["atr14_pips"].values
    d2low = M5["dist_to_today_low_pips"].values

    filt = []
    for _, p in piv.iterrows():
        pi = int(p["pi"])
        if not (6 <= atr14[pi] <= 11): continue
        if d2low[pi] > 80: continue
        if p["confirm_lag"] > 8: continue
        if p["pivot_time"] < M1.index[0]: continue
        filt.append(p)
    piv_filt = pd.DataFrame(filt)
    print(f"\nFiltered + in M1 window: {len(piv_filt)}")
    print(f"BUY:  {(~piv_filt['is_high']).sum()}")
    print(f"SELL: {piv_filt['is_high'].sum()}")

    M1H = M1["high"].values; M1L = M1["low"].values; M1C = M1["close"].values
    m1_idx = pd.Series(range(len(M1)), index=M1.index)

    def simulate(retrace, sl, is_high):
        rows = []
        for _, p in piv_filt[piv_filt["is_high"] == is_high].iterrows():
            pivot_px = p["price"]
            trig_px = pivot_px - retrace*PIP if is_high else pivot_px + retrace*PIP
            # Find first M1 bar at or after pivot_time
            idx = M1.index.searchsorted(p["pivot_time"])
            if idx >= len(M1): continue
            start = int(idx); trig = None
            for k in range(60):
                j = start + k
                if j >= len(M1): break
                if is_high and M1L[j] <= trig_px: trig = j; break
                if (not is_high) and M1H[j] >= trig_px: trig = j; break
            if trig is None: continue
            entry = M1C[trig]
            end = min(trig + 60, len(M1))
            mfe = mae = 0.0
            for k in range(trig+1, end):
                if is_high:
                    fav = (entry - M1L[k])/PIP; adv = (M1H[k] - entry)/PIP
                else:
                    fav = (M1H[k] - entry)/PIP; adv = (entry - M1L[k])/PIP
                if fav > mfe: mfe = fav
                if adv > mae: mae = adv
            net = -sl if mae >= sl else max(mfe - sl, 0)
            rows.append({"month": p["pivot_time"].strftime("%Y-%m"),
                         "pivot_time": p["pivot_time"], "entry_lag_min": trig-start,
                         "mfe": mfe, "mae": mae, "net": net})
        return pd.DataFrame(rows)

    print(f"\n{'='*78}\nEXTENDED M1 — full 5-month OOS validation\n{'='*78}")
    for side, ih in [("BUY", False), ("SELL", True)]:
        for retrace in [3, 5, 8, 10]:
            t = simulate(retrace, 10, ih)
            if len(t) == 0: continue
            print(f"\n{side} @ retrace={retrace}pip, SL=10:  n={len(t)}  "
                  f"avg net={t['net'].mean():+.2f}  WR={100*(t['net']>0).mean():.0f}%  "
                  f"total={t['net'].sum():+.0f}")
            print("    Per-month:")
            by_m = t.groupby("month").agg(n=("net","size"), wins=("net", lambda x: (x>0).sum()),
                                           avg=("net","mean"), total=("net","sum")).round(2)
            for m, r in by_m.iterrows():
                print(f"      {m}: n={int(r['n'])}  wins={int(r['wins'])}  "
                      f"avg={r['avg']:+5.1f}  total={r['total']:+5.0f}")

    print(f"\n{'='*78}\nFINAL RECOMMENDATION — retrace=5pip, SL=10, both sides combined\n{'='*78}")
    t_buy  = simulate(5, 10, False)
    t_sell = simulate(5, 10, True)
    t_all = pd.concat([t_buy.assign(side="BUY"), t_sell.assign(side="SELL")], ignore_index=True)
    print(f"  Total trades: {len(t_all)}  ({len(t_buy)} BUY + {len(t_sell)} SELL)")
    print(f"  Combined avg net: {t_all['net'].mean():+.2f} pips/trade")
    print(f"  Combined WR: {100*(t_all['net']>0).mean():.0f}%")
    print(f"  Combined total: {t_all['net'].sum():+.0f} pips over {len(t_all)} trades")
    print(f"  Per month combined:")
    bm = t_all.groupby("month").agg(n=("net","size"), avg=("net","mean"), total=("net","sum")).round(2)
    for m, r in bm.iterrows():
        print(f"    {m}: n={int(r['n']):2d}  avg={r['avg']:+5.1f}  total={r['total']:+6.0f}")


if __name__ == "__main__":
    main()
