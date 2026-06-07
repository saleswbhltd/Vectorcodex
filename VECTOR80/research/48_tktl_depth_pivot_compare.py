"""
Step 48 - Rebuild TKTL003/ZZLEG001 structural pivots from M5 broker data.

TKTL003 loads "Market\\ZigZag Lines MTF for MT5", but for confirmed
historical pivots it deliberately falls back to an OHLC symmetric-window scan:

  - M5 timeframe by default
  - InpZZDepth = 12
  - pivot HIGH: High[i] strictly greater than every High in +/- depth bars
  - pivot LOW:  Low[i]  strictly lower   than every Low  in +/- depth bars
  - consecutive same-side pivots are collapsed, keeping the more extreme one

This script applies that same map engine to broker M5 bars and Dukascopy M5
bars, then compares pivot time/price/type/label matches.

Example:
  python3 48_tktl_depth_pivot_compare.py \
    --broker-m5 BROKER_TICKS_EURUSD_20250201_20250601_shift-3h_broker_m5.csv \
    --duka-m5 BROKER_TICKS_EURUSD_20250201_20250601_shift-3h_duka_overlap_m5.csv
"""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass

import numpy as np
import pandas as pd


PIP = 0.0001
OUT_DIR = "/home/cmake/Vector/research"


@dataclass(frozen=True)
class Pivot:
    idx: int
    pivot_time: pd.Timestamp
    price: float
    side: str


def load_m5(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    if "datetime" not in df.columns:
        first = df.columns[0]
        df = df.rename(columns={first: "datetime"})
    df["datetime"] = pd.to_datetime(df["datetime"], utc=True, format="mixed").dt.tz_localize(None)
    for c in ["open", "high", "low", "close", "tick_count", "spread_avg_pips"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["datetime", "high", "low"]).sort_values("datetime")
    df = df.drop_duplicates("datetime").set_index("datetime")
    return df


def detect_tktl_depth_pivots(m5: pd.DataFrame, depth: int = 12) -> pd.DataFrame:
    """Mimic ZZLEG001 v2's series-array scan and same-side dedup."""
    h = m5["high"].to_numpy(dtype=float)
    l = m5["low"].to_numpy(dtype=float)
    times = m5.index.to_numpy()
    n = len(m5)

    raw: list[Pivot] = []
    if n < depth * 2 + 1:
        return empty_pivot_frame()

    # MQL5 series arrays are newest->oldest. Loop in the same order to match
    # ZZLEG001's same-side cleanup decisions.
    for series_i in range(depth, n - depth):
        chrono_i = n - 1 - series_i
        lo = chrono_i - depth
        hi = chrono_i + depth + 1
        cur_h = h[chrono_i]
        cur_l = l[chrono_i]
        is_high = bool(np.all(np.delete(h[lo:hi], depth) < cur_h))
        is_low = bool(np.all(np.delete(l[lo:hi], depth) > cur_l))
        if is_high:
            raw.append(Pivot(chrono_i, pd.Timestamp(times[chrono_i]), round(float(cur_h), 5), "HIGH"))
        elif is_low:
            raw.append(Pivot(chrono_i, pd.Timestamp(times[chrono_i]), round(float(cur_l), 5), "LOW"))

    clean: list[Pivot] = []
    for p in raw:
        if not clean:
            clean.append(p)
            continue
        last = clean[-1]
        if last.side == p.side:
            if p.side == "HIGH" and p.price > last.price:
                clean[-1] = p
            elif p.side == "LOW" and p.price < last.price:
                clean[-1] = p
        else:
            clean.append(p)

    # Clean list is newest->oldest; maps are easier to reason about oldest->newest.
    rows = []
    prev_high = None
    prev_low = None
    for p in reversed(clean):
        if p.side == "HIGH":
            label = "H0" if prev_high is None else ("HH" if p.price > prev_high else "LH")
            prev_high = p.price
        else:
            label = "L0" if prev_low is None else ("HL" if p.price > prev_low else "LL")
            prev_low = p.price
        rows.append(
            {
                "pivot_time": p.pivot_time,
                "bar_index": p.idx,
                "price": p.price,
                "side": p.side,
                "label": label,
            }
        )
    return pd.DataFrame(rows)


def empty_pivot_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=["pivot_time", "bar_index", "price", "side", "label"])


def count_labels(p: pd.DataFrame) -> dict[str, int]:
    order = ["H0", "HH", "LH", "L0", "HL", "LL"]
    return p["label"].value_counts().reindex(order).fillna(0).astype(int).to_dict()


def exact_compare(broker_p: pd.DataFrame, duka_p: pd.DataFrame) -> pd.DataFrame:
    cols = ["pivot_time", "price", "side", "label"]
    return broker_p[cols].merge(duka_p[cols], on=cols, how="outer", indicator=True)


def nearest_time_stats(
    broker_p: pd.DataFrame,
    duka_p: pd.DataFrame,
    tolerance_minutes: list[int],
) -> pd.DataFrame:
    rows = []
    if broker_p.empty or duka_p.empty:
        return pd.DataFrame(rows)

    for label_sensitive in [False, True]:
        for tol in tolerance_minutes:
            matched_broker = set()
            matched_duka = set()
            for bi, b in broker_p.iterrows():
                cand = duka_p[duka_p["side"].eq(b["side"])].copy()
                if label_sensitive:
                    cand = cand[cand["label"].eq(b["label"])]
                if cand.empty:
                    continue
                dt = (cand["pivot_time"] - b["pivot_time"]).abs()
                ok = dt <= pd.Timedelta(minutes=tol)
                if not ok.any():
                    continue
                sub = cand.loc[ok].copy()
                sub["_dt"] = dt.loc[ok]
                sub["_price_pips"] = (sub["price"] - b["price"]).abs() / PIP
                sub = sub.sort_values(["_dt", "_price_pips"])
                di = int(sub.index[0])
                if di in matched_duka:
                    continue
                matched_broker.add(int(bi))
                matched_duka.add(di)
            rows.append(
                {
                    "match_mode": "side+label" if label_sensitive else "side",
                    "tolerance_minutes": tol,
                    "matches": len(matched_broker),
                    "broker_recall": len(matched_broker) / len(broker_p),
                    "duka_recall": len(matched_duka) / len(duka_p),
                }
            )
    return pd.DataFrame(rows)


def price_error_stats(broker_p: pd.DataFrame, duka_p: pd.DataFrame, tol_minutes: int = 5) -> dict[str, float]:
    errors = []
    for _, b in broker_p.iterrows():
        cand = duka_p[duka_p["side"].eq(b["side"])].copy()
        if cand.empty:
            continue
        dt = (cand["pivot_time"] - b["pivot_time"]).abs()
        cand = cand.loc[dt <= pd.Timedelta(minutes=tol_minutes)].copy()
        if cand.empty:
            continue
        cand["_dt"] = dt.loc[cand.index]
        cand["_price_pips"] = (cand["price"] - b["price"]).abs() / PIP
        errors.append(float(cand.sort_values(["_dt", "_price_pips"])["_price_pips"].iloc[0]))
    if not errors:
        return {"n": 0, "mean_abs_pips": np.nan, "median_abs_pips": np.nan, "p95_abs_pips": np.nan}
    arr = np.asarray(errors)
    return {
        "n": int(len(arr)),
        "mean_abs_pips": float(np.mean(arr)),
        "median_abs_pips": float(np.median(arr)),
        "p95_abs_pips": float(np.percentile(arr, 95)),
    }


def write_report(
    out_path: str,
    broker_m5: pd.DataFrame,
    duka_m5: pd.DataFrame,
    broker_p: pd.DataFrame,
    duka_p: pd.DataFrame,
    cmp: pd.DataFrame,
    tol_stats: pd.DataFrame,
    price_stats: dict[str, float],
    depth: int,
) -> None:
    exact = int((cmp["_merge"] == "both").sum())
    if tol_stats.empty:
        tol_md = "No nearest-time matches."
    else:
        tol_md = "\n".join(
            [
                "| match_mode | tolerance_minutes | matches | broker_recall | duka_recall |",
                "|---|---:|---:|---:|---:|",
            ]
            + [
                f"| {r.match_mode} | {int(r.tolerance_minutes)} | {int(r.matches)} | "
                f"{float(r.broker_recall):.3f} | {float(r.duka_recall):.3f} |"
                for r in tol_stats.itertuples(index=False)
            ]
        )
    lines = [
        "# TKTL003 / ZZLEG001 Depth Pivot Compare",
        "",
        f"Depth: `{depth}` M5 bars each side",
        "",
        "Confirmed historical pivots are rebuilt from OHLC because TKTL003 marks the indicator's confirmed buffers as unreliable in Strategy Tester.",
        "",
        "## Bar overlap",
        "",
        f"- Broker M5 bars: `{len(broker_m5):,}` from `{broker_m5.index.min()}` to `{broker_m5.index.max()}`",
        f"- Dukascopy M5 bars: `{len(duka_m5):,}` from `{duka_m5.index.min()}` to `{duka_m5.index.max()}`",
        "",
        "## Pivot counts",
        "",
        f"- Broker pivots: `{len(broker_p):,}` {count_labels(broker_p)}",
        f"- Dukascopy pivots: `{len(duka_p):,}` {count_labels(duka_p)}",
        f"- Exact matches by time + price + side + label: `{exact}`",
        f"- Broker only exact rows: `{int((cmp['_merge'] == 'left_only').sum())}`",
        f"- Dukascopy only exact rows: `{int((cmp['_merge'] == 'right_only').sum())}`",
        "",
        "## Nearest-time matches",
        "",
        tol_md,
        "",
        "## Price error for same-side pivots within 5 minutes",
        "",
        f"- Matched pivots: `{price_stats['n']}`",
        f"- Mean absolute price error: `{price_stats['mean_abs_pips']:.2f}` pips",
        f"- Median absolute price error: `{price_stats['median_abs_pips']:.2f}` pips",
        f"- 95th percentile absolute price error: `{price_stats['p95_abs_pips']:.2f}` pips",
        "",
    ]
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--broker-m5", default=f"{OUT_DIR}/BROKER_TICKS_EURUSD_20250201_20250601_shift-3h_broker_m5.csv")
    ap.add_argument("--duka-m5", default=f"{OUT_DIR}/BROKER_TICKS_EURUSD_20250201_20250601_shift-3h_duka_overlap_m5.csv")
    ap.add_argument("--depth", type=int, default=12)
    ap.add_argument("--tag", default=None)
    args = ap.parse_args()

    broker_m5 = load_m5(args.broker_m5)
    duka_m5 = load_m5(args.duka_m5)
    common = broker_m5.index.intersection(duka_m5.index)
    broker_m5 = broker_m5.loc[common]
    duka_m5 = duka_m5.loc[common]

    broker_p = detect_tktl_depth_pivots(broker_m5, args.depth)
    duka_p = detect_tktl_depth_pivots(duka_m5, args.depth)
    cmp = exact_compare(broker_p, duka_p)
    tol_stats = nearest_time_stats(broker_p, duka_p, [0, 5, 10, 15, 30, 60])
    price_stats = price_error_stats(broker_p, duka_p, 5)

    tag = args.tag
    if tag is None:
        stem = os.path.splitext(os.path.basename(args.broker_m5))[0]
        tag = stem.replace("_broker_m5", "")

    out_b = f"{OUT_DIR}/{tag}_tktl_depth{args.depth}_broker_pivots.csv"
    out_d = f"{OUT_DIR}/{tag}_tktl_depth{args.depth}_duka_pivots.csv"
    out_c = f"{OUT_DIR}/{tag}_tktl_depth{args.depth}_pivot_compare.csv"
    out_s = f"{OUT_DIR}/{tag}_tktl_depth{args.depth}_match_stats.csv"
    out_r = f"{OUT_DIR}/{tag}_tktl_depth{args.depth}_report.md"

    broker_p.to_csv(out_b, index=False)
    duka_p.to_csv(out_d, index=False)
    cmp.to_csv(out_c, index=False)
    tol_stats.to_csv(out_s, index=False)
    write_report(out_r, broker_m5, duka_m5, broker_p, duka_p, cmp, tol_stats, price_stats, args.depth)

    print(f"common M5 bars: {len(common):,}")
    print(f"broker pivots: {len(broker_p):,} {count_labels(broker_p)}")
    print(f"duka pivots:   {len(duka_p):,} {count_labels(duka_p)}")
    print(f"exact matches: {int((cmp['_merge'] == 'both').sum()):,}")
    print("\nnearest-time matches:")
    print(tol_stats.to_string(index=False, float_format=lambda x: f"{x:.3f}"))
    print("\nprice error for same-side pivots within 5 minutes:")
    print(price_stats)
    print("\nSaved:")
    print(f"  {out_b}")
    print(f"  {out_d}")
    print(f"  {out_c}")
    print(f"  {out_s}")
    print(f"  {out_r}")


if __name__ == "__main__":
    main()
