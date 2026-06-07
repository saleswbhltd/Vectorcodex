"""
Step 25 — INVERTED METHODOLOGY: hunt for indicators that fire AT the pivot bar.

Ground truth: historical ZigZag pivots (we trust ZZ as the labeller).
Question:     which indicator state at the same bar identifies a pivot
              in real time, before ZZ would confirm?

For each candidate signal generator, compute:
  precision = (signals on bars within ±tolerance of a real pivot) / total signals
  recall    = (real pivots with a candidate signal within ±tolerance) / total pivots
  F1        = 2·precision·recall / (precision + recall)

Goal: find generators reaching ≥80% precision with usable recall.

Outputs:
  candidate_ranking.csv  full ranking of all generators tested
  CANDIDATE_TOP.md       human-readable top performers + analysis
"""

import pandas as pd
import numpy as np

DATA = "/home/cmake/Vector/research/m5_2026_deep.csv.gz"
OUT_RANK = "/home/cmake/Vector/research/candidate_ranking.csv"
OUT_MD   = "/home/cmake/Vector/research/CANDIDATE_TOP.md"

# Tolerance in M5 bars — a candidate "matches" a ZZ pivot if it fires within
# ±TOL bars of the pivot. TOL=0 = same bar only. TOL=1 = ±5min.
TOL = 1

# ZZ thresholds to try as ground truth
ZZ_THRESHOLDS = [15, 20, 25, 30]


def detect_pivots(df, thresh_pips, pip=0.0001):
    thresh = thresh_pips * pip
    h = df["high"].values; l = df["low"].values; t = df.index.values
    if len(df) < 3: return pd.DataFrame()
    direction_up = h[1] >= h[0]
    ext = h[1] if direction_up else l[1]; ext_i = 1
    out = []
    for i in range(2, len(df)):
        if direction_up:
            if h[i] > ext: ext, ext_i = h[i], i
            elif l[i] <= ext - thresh:
                out.append((t[ext_i], ext_i, ext, True))
                direction_up = False; ext, ext_i = l[i], i
        else:
            if l[i] < ext: ext, ext_i = l[i], i
            elif h[i] >= ext + thresh:
                out.append((t[ext_i], ext_i, ext, False))
                direction_up = True; ext, ext_i = h[i], i
    return pd.DataFrame(out, columns=["pivot_time", "pivot_idx", "price", "is_high"])


def score_candidate(name, mask, pivot_mask, tol):
    """
    Compute precision/recall/F1.
    mask         : Boolean Series — when this candidate signal fires
    pivot_mask   : Boolean Series — bars that are real pivots of the right type
    tol          : how many bars before/after a pivot still count as a match
    """
    if mask.sum() == 0:
        return None
    # Expand pivot zone to ±tol bars
    if tol > 0:
        pivot_zone = pivot_mask.rolling(window=2*tol+1, center=True, min_periods=1).max() > 0
    else:
        pivot_zone = pivot_mask
    matches    = (mask & pivot_zone).sum()
    signals    = int(mask.sum())
    real_pivots = int(pivot_mask.sum())
    precision  = matches / signals if signals > 0 else 0
    # Recall: count distinct pivots covered (a single pivot can be covered by ≥1 candidate)
    if tol > 0:
        signal_zone = mask.rolling(window=2*tol+1, center=True, min_periods=1).max() > 0
    else:
        signal_zone = mask
    covered    = (pivot_mask & signal_zone).sum()
    recall     = covered / real_pivots if real_pivots > 0 else 0
    f1         = 2*precision*recall/(precision+recall) if (precision+recall) > 0 else 0
    return {"candidate": name, "signals": signals, "matches": int(matches),
            "real_pivots": real_pivots, "precision": precision,
            "recall": recall, "f1": f1}


def build_candidates(df):
    """Generate a battery of candidate signal masks. Each entry is (name, mask, target_side)."""
    o, h, l, c = df["open"], df["high"], df["low"], df["close"]
    cs = []                       # candidate signals list

    # ── RSI extremes ──
    for x in [65, 70, 72, 75, 78, 80]:
        cs.append((f"rsi14>{x}", df["rsi14"] > x, "SELL"))
    for x in [20, 22, 25, 28, 30, 35]:
        cs.append((f"rsi14<{x}", df["rsi14"] < x, "BUY"))

    # ── Stochastic extremes ──
    for x in [75, 80, 85, 90]:
        cs.append((f"stoch_k>{x}", df["stoch_k"] > x, "SELL"))
        cs.append((f"stoch_k>{x}&d>{x}", (df["stoch_k"] > x) & (df["stoch_d"] > x), "SELL"))
    for x in [10, 15, 20, 25]:
        cs.append((f"stoch_k<{x}", df["stoch_k"] < x, "BUY"))
        cs.append((f"stoch_k<{x}&d<{x}", (df["stoch_k"] < x) & (df["stoch_d"] < x), "BUY"))

    # ── Williams %R ──
    for x in [-5, -10, -15, -20]:
        cs.append((f"williams>{x}", df["williams_r14"] > x, "SELL"))
    for x in [-95, -90, -85, -80]:
        cs.append((f"williams<{x}", df["williams_r14"] < x, "BUY"))

    # ── BB breach ──
    cs.append(("bb_breach_up",   df["bb_breach_up"] == 1, "SELL"))
    cs.append(("bb_breach_dn",   df["bb_breach_dn"] == 1, "BUY"))
    for x in [0.95, 0.98, 1.00, 1.02]:
        cs.append((f"bb_pctB>{x}", df["bb_pctB"] > x, "SELL"))
    for x in [-0.02, 0.00, 0.02, 0.05]:
        cs.append((f"bb_pctB<{x}", df["bb_pctB"] < x, "BUY"))

    # ── Candle patterns ──
    cs.append(("is_pin_bear",    df["is_pin_bear"] == 1, "SELL"))
    cs.append(("is_pin_bull",    df["is_pin_bull"] == 1, "BUY"))
    cs.append(("is_eng_bear",    df["is_eng_bear"] == 1, "SELL"))
    cs.append(("is_eng_bull",    df["is_eng_bull"] == 1, "BUY"))
    for x in [0.55, 0.65, 0.75]:
        cs.append((f"upper_wick>{x}",  df["upper_wick_ratio"] > x, "SELL"))
        cs.append((f"lower_wick>{x}",  df["lower_wick_ratio"] > x, "BUY"))

    # ── Consecutive bars (momentum streaks → exhaustion) ──
    for x in [3, 4, 5, 6, 7]:
        cs.append((f"consec_up>={x}", df["consec_up"] >= x, "SELL"))
        cs.append((f"consec_dn>={x}", df["consec_dn"] >= x, "BUY"))

    # ── Local extreme (the bar IS the max/min of last N) ──
    for n in [3, 5, 7, 10, 15, 20]:
        cs.append((f"local_max_{n}", df["high"] == df["high"].rolling(n).max(), "SELL"))
        cs.append((f"local_min_{n}", df["low"]  == df["low"].rolling(n).min(),  "BUY"))

    # ── Overextension from EMA20 in ATR units ──
    for x in [1.5, 2.0, 2.5, 3.0]:
        cs.append((f"dist_ema20_atr>{x}",  df["dist_ema20_atr"] >  x, "SELL"))
        cs.append((f"dist_ema20_atr<-{x}", df["dist_ema20_atr"] < -x, "BUY"))

    # ── RSI divergence flags (we already built these) ──
    cs.append(("rsi_div_bear",   df["rsi_div_bear"] == 1, "SELL"))
    cs.append(("rsi_div_bull",   df["rsi_div_bull"] == 1, "BUY"))
    cs.append(("macd_div_bear",  df["macd_div_bear"] == 1, "SELL"))
    cs.append(("macd_div_bull",  df["macd_div_bull"] == 1, "BUY"))

    # ── Range climax (vol blow-out at extremes) ──
    cs.append(("range_climax",   df["range_climax"] == 1, "SELL"))  # ambiguous side
    cs.append(("vol_climax",     df["vol_climax"]   == 1, "SELL"))

    # ── Compound: local max + RSI elevated ──
    for n_local in [5, 10]:
        for r in [60, 65, 70]:
            mask = (df["high"] == df["high"].rolling(n_local).max()) & (df["rsi14"] > r)
            cs.append((f"local_max_{n_local}&rsi>{r}", mask, "SELL"))
            mask = (df["low"]  == df["low"].rolling(n_local).min())  & (df["rsi14"] < (100-r))
            cs.append((f"local_min_{n_local}&rsi<{100-r}", mask, "BUY"))

    # ── Compound: local max + pin bar ──
    for n_local in [5, 10]:
        mask = (df["high"] == df["high"].rolling(n_local).max()) & (df["is_pin_bear"] == 1)
        cs.append((f"local_max_{n_local}&pin_bear", mask, "SELL"))
        mask = (df["low"]  == df["low"].rolling(n_local).min())  & (df["is_pin_bull"] == 1)
        cs.append((f"local_min_{n_local}&pin_bull", mask, "BUY"))

    # ── Compound: local max + upper wick rejection ──
    for n_local in [5, 10]:
        for w in [0.5, 0.6]:
            mask = (df["high"] == df["high"].rolling(n_local).max()) & (df["upper_wick_ratio"] > w)
            cs.append((f"local_max_{n_local}&upper_wick>{w}", mask, "SELL"))
            mask = (df["low"]  == df["low"].rolling(n_local).min())  & (df["lower_wick_ratio"] > w)
            cs.append((f"local_min_{n_local}&lower_wick>{w}", mask, "BUY"))

    # ── Compound: local max + bb upper breach + RSI elevated ──
    mask = (df["high"] == df["high"].rolling(10).max()) & (df["bb_pctB"] > 0.95) & (df["rsi14"] > 60)
    cs.append(("local_max_10&bbB>0.95&rsi>60", mask, "SELL"))
    mask = (df["low"]  == df["low"].rolling(10).min())  & (df["bb_pctB"] < 0.05) & (df["rsi14"] < 40)
    cs.append(("local_min_10&bbB<0.05&rsi<40", mask, "BUY"))

    return cs


def main():
    print("loading...")
    df = pd.read_csv(DATA, index_col=0, parse_dates=True)
    print(f"  {len(df):,} M5 bars  ({df.index[0]} → {df.index[-1]})")

    all_rows = []
    for thresh in ZZ_THRESHOLDS:
        piv = detect_pivots(df, thresh)
        if piv.empty: continue
        sell_pivots = df.index.isin(piv[piv["is_high"]]["pivot_time"])
        buy_pivots  = df.index.isin(piv[~piv["is_high"]]["pivot_time"])
        sell_mask = pd.Series(sell_pivots, index=df.index)
        buy_mask  = pd.Series(buy_pivots, index=df.index)
        print(f"\n=== Ground truth: ZZ {thresh}pip → {sell_mask.sum()} SELL + {buy_mask.sum()} BUY pivots ===")

        cs = build_candidates(df)
        for name, mask, side in cs:
            mask = mask.reindex(df.index).fillna(False)
            target = sell_mask if side == "SELL" else buy_mask
            res = score_candidate(name, mask, target, TOL)
            if res:
                res["zz_thresh"] = thresh
                res["side"] = side
                all_rows.append(res)

    rank = pd.DataFrame(all_rows)
    rank = rank.sort_values(["zz_thresh", "side", "f1"], ascending=[True, True, False])
    rank.to_csv(OUT_RANK, index=False, float_format="%.4f")
    print(f"\nfull ranking → {OUT_RANK}  ({len(rank)} rows)")

    # Headline: top by precision (filter to min recall and meaningful signal count)
    out_lines = []
    out_lines.append("# Candidate Signal Ranking — Inverted Methodology")
    out_lines.append("")
    out_lines.append("**Goal:** find indicator states that fire AT the pivot bar with ≥80% precision "
                     "(real-time pivot identification, before ZZ would confirm).")
    out_lines.append(f"**Match tolerance:** ±{TOL} M5 bars from a real ZZ pivot.")
    out_lines.append("")

    for thresh in ZZ_THRESHOLDS:
        for side in ["SELL", "BUY"]:
            sub = rank[(rank["zz_thresh"] == thresh) & (rank["side"] == side)]
            if sub.empty: continue
            # Show top 10 by F1 with at least 20 signals
            top = sub[sub["signals"] >= 20].head(15)
            out_lines.append(f"\n## Top {side} candidates vs ZZ {thresh}pip pivots")
            out_lines.append("")
            out_lines.append(f"| Candidate | Signals | Matches | Real pivots | Precision | Recall | F1 |")
            out_lines.append(f"|---|---|---|---|---|---|---|")
            for _, r in top.iterrows():
                out_lines.append(f"| `{r['candidate']}` | {r['signals']} | {r['matches']} | "
                                 f"{r['real_pivots']} | {100*r['precision']:.1f}% | "
                                 f"{100*r['recall']:.1f}% | {r['f1']:.3f} |")
            # Show ≥80% precision candidates separately
            best = sub[(sub["precision"] >= 0.80) & (sub["signals"] >= 10)].head(15)
            if not best.empty:
                out_lines.append(f"\n### ≥80% precision (the holy grail)")
                out_lines.append(f"| Candidate | Signals | Precision | Recall | F1 |")
                out_lines.append(f"|---|---|---|---|---|")
                for _, r in best.iterrows():
                    out_lines.append(f"| `{r['candidate']}` | {r['signals']} | "
                                     f"{100*r['precision']:.1f}% | {100*r['recall']:.1f}% | {r['f1']:.3f} |")
            else:
                out_lines.append(f"\n### ≥80% precision: NONE with ≥10 signals.")

    with open(OUT_MD, "w") as f:
        f.write("\n".join(out_lines))
    print(f"summary → {OUT_MD}")

    # Print quick on-screen summary
    print("\n" + "="*78)
    print("HEADLINE — top 5 by F1 per zz_thresh × side")
    print("="*78)
    for thresh in ZZ_THRESHOLDS:
        for side in ["SELL", "BUY"]:
            sub = rank[(rank["zz_thresh"]==thresh) & (rank["side"]==side) & (rank["signals"] >= 20)]
            if sub.empty: continue
            print(f"\n— ZZ{thresh}pip {side} —")
            for _, r in sub.head(5).iterrows():
                print(f"  {r['candidate']:35s}  n={int(r['signals']):4d}  "
                      f"prec={100*r['precision']:5.1f}%  rec={100*r['recall']:5.1f}%  F1={r['f1']:.3f}")


if __name__ == "__main__":
    main()
