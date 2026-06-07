"""
Step 26 — Combination search.

Single indicators top out at ~19% precision. Hypothesis: precision rises sharply
when MULTIPLE independent signals agree. Two approaches tested:

  K-of-N voting: signal fires when ≥K of N candidate conditions are simultaneously true.
                  More restrictive than single conditions; lower signal count, higher precision.

  Strict AND chains: only the very tight intersections of 3-5 conditions.

Also tries ±2 and ±3 bar tolerance — pivot bar identification within 2-3 bars is still
adequate for entry within 0-10 points if M5 bar = 5 min.
"""

import pandas as pd
import numpy as np
import itertools

DATA = "/home/cmake/Vector/research/m5_2026_deep.csv.gz"
OUT_MD = "/home/cmake/Vector/research/COMBO_TOP.md"
OUT_RANK = "/home/cmake/Vector/research/combo_ranking.csv"

ZZ_THRESH = 20         # focus on 20-pip ZZ pivots (matches earlier analyses)
TOLERANCES = [0, 1, 2, 3]
PIP = 0.0001


def detect_pivots(df, thresh_pips):
    thresh = thresh_pips * PIP
    h = df["high"].values; l = df["low"].values; t = df.index.values
    direction_up = h[1] >= h[0]
    ext = h[1] if direction_up else l[1]; ext_i = 1
    out = []
    for i in range(2, len(df)):
        if direction_up:
            if h[i] > ext: ext, ext_i = h[i], i
            elif l[i] <= ext - thresh:
                out.append((t[ext_i], True))
                direction_up = False; ext, ext_i = l[i], i
        else:
            if l[i] < ext: ext, ext_i = l[i], i
            elif h[i] >= ext + thresh:
                out.append((t[ext_i], False))
                direction_up = True; ext, ext_i = h[i], i
    return out


def score(mask, pivot_mask, tol):
    """Vectorised precision / recall / F1 with ±tol bar tolerance."""
    n_sig = int(mask.sum())
    if n_sig == 0: return None
    if tol > 0:
        pivot_zone = pivot_mask.rolling(window=2*tol+1, center=True, min_periods=1).max() > 0
        signal_zone = mask.rolling(window=2*tol+1, center=True, min_periods=1).max() > 0
    else:
        pivot_zone, signal_zone = pivot_mask, mask
    matches = int((mask & pivot_zone).sum())
    covered = int((pivot_mask & signal_zone).sum())
    n_piv   = int(pivot_mask.sum())
    prec = matches / n_sig if n_sig > 0 else 0
    rec  = covered / n_piv if n_piv > 0 else 0
    f1   = 2*prec*rec/(prec+rec) if (prec+rec) > 0 else 0
    return {"signals": n_sig, "matches": matches, "covered": covered,
            "real_pivots": n_piv, "precision": prec, "recall": rec, "f1": f1}


def main():
    df = pd.read_csv(DATA, index_col=0, parse_dates=True)
    print(f"loaded {len(df):,} bars")

    pivots = detect_pivots(df, ZZ_THRESH)
    sell_p = pd.Series(
        df.index.isin([t for t, is_h in pivots if is_h]), index=df.index)
    buy_p  = pd.Series(
        df.index.isin([t for t, is_h in pivots if not is_h]), index=df.index)
    print(f"ZZ {ZZ_THRESH}pip → {sell_p.sum()} SELL + {buy_p.sum()} BUY pivots")

    # ── Per-side condition libraries ──
    sell_conds = {
        "local_max_10":        df["high"] == df["high"].rolling(10).max(),
        "local_max_20":        df["high"] == df["high"].rolling(20).max(),
        "rsi>70":              df["rsi14"] > 70,
        "rsi>75":              df["rsi14"] > 75,
        "stoch_k>80":          df["stoch_k"] > 80,
        "bb_pctB>0.95":        df["bb_pctB"] > 0.95,
        "bb_breach_up":        df["bb_breach_up"] == 1,
        "upper_wick>0.55":     df["upper_wick_ratio"] > 0.55,
        "is_pin_bear":         df["is_pin_bear"] == 1,
        "consec_up>=3":        df["consec_up"] >= 3,
        "consec_up>=5":        df["consec_up"] >= 5,
        "williams>-10":        df["williams_r14"] > -10,
        "dist_ema20_atr>2":    df["dist_ema20_atr"] > 2.0,
        "rsi_div_bear":        df["rsi_div_bear"] == 1,
    }
    buy_conds = {
        "local_min_10":        df["low"] == df["low"].rolling(10).min(),
        "local_min_20":        df["low"] == df["low"].rolling(20).min(),
        "rsi<30":              df["rsi14"] < 30,
        "rsi<25":              df["rsi14"] < 25,
        "stoch_k<20":          df["stoch_k"] < 20,
        "bb_pctB<0.05":        df["bb_pctB"] < 0.05,
        "bb_breach_dn":        df["bb_breach_dn"] == 1,
        "lower_wick>0.55":     df["lower_wick_ratio"] > 0.55,
        "is_pin_bull":         df["is_pin_bull"] == 1,
        "consec_dn>=3":        df["consec_dn"] >= 3,
        "consec_dn>=5":        df["consec_dn"] >= 5,
        "williams<-90":        df["williams_r14"] < -90,
        "dist_ema20_atr<-2":   df["dist_ema20_atr"] < -2.0,
        "rsi_div_bull":        df["rsi_div_bull"] == 1,
    }

    all_results = []

    for side_label, conds, target in [("SELL", sell_conds, sell_p),
                                       ("BUY",  buy_conds,  buy_p)]:
        print(f"\n=== {side_label} side — {len(conds)} conditions ===")

        # ── 1. K-of-N voting ──
        N = len(conds)
        cond_df = pd.DataFrame(conds).astype(int)
        cond_sum = cond_df.sum(axis=1)
        print(f"K-of-{N} voting (tolerance ±1):")
        for k in range(3, N+1):
            mask = (cond_sum >= k)
            r = score(mask, target, 1)
            if r is None: continue
            r.update({"side": side_label, "type": "K-of-N",
                      "rule": f"K>={k} of {N}", "tol": 1})
            all_results.append(r.copy())
            if r["signals"] > 0 and r["signals"] < 5000:
                print(f"  K>={k}: n={r['signals']:5d} prec={100*r['precision']:5.1f}% "
                      f"rec={100*r['recall']:5.1f}% F1={r['f1']:.3f}")

        # ── 2. Strict 3-AND combinations (best precision targets) ──
        print(f"3-way AND combinations (top by precision, tol±1):")
        combos = list(itertools.combinations(list(conds.items()), 3))
        combo_rows = []
        for triplet in combos:
            mask = triplet[0][1] & triplet[1][1] & triplet[2][1]
            n_sig = mask.sum()
            if n_sig < 10 or n_sig > 2000: continue
            r = score(mask, target, 1)
            if r is None: continue
            name = " & ".join(t[0] for t in triplet)
            r.update({"side": side_label, "type": "3-AND",
                      "rule": name, "tol": 1})
            combo_rows.append(r)
            all_results.append(r.copy())
        # Show top 10 by precision (with >=20 signals so it's not noise)
        sorted_combos = sorted([r for r in combo_rows if r["signals"] >= 20],
                                key=lambda x: -x["precision"])[:10]
        for r in sorted_combos:
            print(f"  {r['rule']:55s} n={r['signals']:4d} prec={100*r['precision']:5.1f}% "
                  f"rec={100*r['recall']:5.1f}% F1={r['f1']:.3f}")

        # ── 3. 4-way ANDs — even tighter ──
        print(f"4-way AND combinations (top by precision, signals >= 10):")
        # Sample limited combinations to avoid combinatorial explosion
        if N <= 10:
            quad_combos = list(itertools.combinations(list(conds.items()), 4))
        else:
            # Just check 4-tuples built from top-8 single performers
            top8 = sorted(conds.items(), key=lambda kv: -score(kv[1], target, 1)["f1"])[:8]
            quad_combos = list(itertools.combinations(top8, 4))
        combo_rows = []
        for q in quad_combos:
            mask = q[0][1] & q[1][1] & q[2][1] & q[3][1]
            n_sig = mask.sum()
            if n_sig < 10 or n_sig > 1000: continue
            r = score(mask, target, 1)
            if r is None: continue
            name = " & ".join(t[0] for t in q)
            r.update({"side": side_label, "type": "4-AND",
                      "rule": name, "tol": 1})
            combo_rows.append(r)
            all_results.append(r.copy())
        sorted_combos = sorted([r for r in combo_rows if r["signals"] >= 10],
                                key=lambda x: -x["precision"])[:10]
        for r in sorted_combos:
            print(f"  {r['rule']:65s} n={r['signals']:4d} prec={100*r['precision']:5.1f}% "
                  f"rec={100*r['recall']:5.1f}% F1={r['f1']:.3f}")

    # ── Tolerance sensitivity for the best findings ──
    print("\n" + "="*78)
    print("TOLERANCE SENSITIVITY for top combinations")
    print("="*78)
    # Pick top-3 per side by precision (with sane signal count)
    rank = pd.DataFrame(all_results)
    rank.to_csv(OUT_RANK, index=False, float_format="%.4f")
    print(f"saved full ranking → {OUT_RANK}")

    for side in ["SELL", "BUY"]:
        sub = rank[(rank["side"] == side) & (rank["signals"] >= 20) &
                    (rank["signals"] <= 500)]
        sub = sub.sort_values("precision", ascending=False).head(5)
        print(f"\n— {side} top 5 (signals 20-500) —")
        target_p = sell_p if side == "SELL" else buy_p
        conds = sell_conds if side == "SELL" else buy_conds
        for _, r in sub.iterrows():
            # Re-build mask & test all tolerances
            parts = [c.strip() for c in r["rule"].split("&")]
            if r["type"] == "K-of-N":
                # Skip for K-of-N as we'd need to rebuild differently
                continue
            mask = None
            for p in parts:
                if p in conds:
                    mask = conds[p] if mask is None else mask & conds[p]
            if mask is None: continue
            print(f"\n  {r['rule']}  (n={int(r['signals'])})")
            for tol in TOLERANCES:
                rr = score(mask, target_p, tol)
                if rr is None: continue
                print(f"    tol=±{tol}: prec={100*rr['precision']:5.1f}%  "
                      f"rec={100*rr['recall']:5.1f}%  F1={rr['f1']:.3f}")


if __name__ == "__main__":
    main()
