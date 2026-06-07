"""
Step 3 — Build a feature matrix per pivot, with forward returns to label good/bad.

For each pivot detected at threshold 15 pips, we capture:
  1. All indicator values at the CONFIRM bar (the earliest a live system could act).
  2. Forward return from the entry price (confirm-bar close, the realistic fill) over
     several horizons — 6, 12, 24, 48, 96 bars (~30min, 1h, 2h, 4h, 8h).
  3. Maximum favourable excursion (MFE) and maximum adverse excursion (MAE) over
     a 24-bar window (2 hours) — the bread-and-butter window for an M5 setup.
  4. A `good` label using a fixed criterion:
       SELL pivot (swing high) good if  MFE_pips_down ≥ R_target  AND  MAE_pips_up ≤ R_stop
       BUY  pivot (swing low ) good if  MFE_pips_up   ≥ R_target  AND  MAE_pips_down ≤ R_stop
     Defaults R_target=15, R_stop=10 — close to "1.5R win without first taking out 1R stop".

We also build a matched RANDOM control sample (5x as many bars as pivots) so we
can compare indicator distributions at pivots vs anywhere.

Reads:  m5_with_indicators.csv.gz, pivots_thresh15.csv
Writes: features_pivots.csv   — one row per confirmed pivot with indicators + labels
        features_random.csv   — matched random non-pivot bars (control)
"""

import pandas as pd
import numpy as np

PIP = 0.0001
THRESH_PIPS = 15
TARGET_PIPS = 15
STOP_PIPS   = 10
LOOKAHEAD_BARS = 24                          # MFE/MAE window
HORIZONS_BARS  = [6, 12, 24, 48, 96]
RNG_SEED = 42

DATA = "/home/cmake/Vector/research/m5_with_indicators.csv.gz"
PIVOTS = f"/home/cmake/Vector/research/pivots_thresh{THRESH_PIPS}.csv"
OUT_PIV = "/home/cmake/Vector/research/features_pivots.csv"
OUT_RND = "/home/cmake/Vector/research/features_random.csv"

# Indicator columns to carry into features (skip OHLC + EMA price levels)
KEEP = [
    "dist_ema20_pips", "dist_ema50_pips", "dist_ema200_pips",
    "rsi14", "stoch_k", "stoch_d", "macd", "macd_sig", "macd_hist",
    "atr14_pips", "bb_pctB", "bb_width_pips",
    "adx14", "plus_di", "minus_di",
    "mom10_pips", "roc10_pct",
    "body_pips", "range_pips", "body_to_range",
    "upper_wick_ratio", "lower_wick_ratio",
    "is_doji", "is_pin_bull", "is_pin_bear", "is_eng_bull", "is_eng_bear",
    "vol_z20", "vol_relvar20",
    "hour_utc", "dow",
]


def compute_forward_metrics(df, idx, is_high, entry_px):
    """
    Forward-window stats from entry index idx to idx+LOOKAHEAD_BARS.
    For a SELL (is_high=True), favourable = DOWN, adverse = UP.
    Returns dict with mfe_pips, mae_pips, hits_target, hits_stop, horizons.
    """
    end = min(idx + LOOKAHEAD_BARS, len(df) - 1)
    if end <= idx:
        return None
    window = df.iloc[idx+1:end+1]
    highs = window["high"].values
    lows  = window["low"].values

    if is_high:                              # SELL — favourable move is DOWN
        mfe_pips = (entry_px - lows.min())  / PIP
        mae_pips = (highs.max() - entry_px) / PIP
    else:                                    # BUY  — favourable move is UP
        mfe_pips = (highs.max() - entry_px) / PIP
        mae_pips = (entry_px - lows.min())  / PIP

    # Horizon-specific returns (close at horizon-N bars)
    out = {"mfe_pips": mfe_pips, "mae_pips": mae_pips}
    for hb in HORIZONS_BARS:
        h_end = min(idx + hb, len(df) - 1)
        c = df["close"].iloc[h_end]
        ret_pips = (entry_px - c) / PIP if is_high else (c - entry_px) / PIP
        out[f"ret_{hb}b_pips"] = ret_pips
    return out


def main():
    print("loading...")
    df = pd.read_csv(DATA, index_col=0, parse_dates=True)
    piv = pd.read_csv(PIVOTS, parse_dates=["pivot_time", "confirm_time"])
    print(f"  {len(df):,} bars, {len(piv):,} pivots")

    # Build a fast lookup of bar index by datetime
    bar_idx = pd.Series(range(len(df)), index=df.index)

    rows = []
    skipped_lookup = 0
    skipped_window = 0
    for _, p in piv.iterrows():
        if p["confirm_time"] not in bar_idx.index:
            skipped_lookup += 1
            continue
        ci = int(bar_idx.loc[p["confirm_time"]])
        # Entry = confirm bar's close (realistic — that's the moment we know)
        entry_px = df["close"].iloc[ci]
        is_high  = bool(p["is_high"])

        fwd = compute_forward_metrics(df, ci, is_high, entry_px)
        if fwd is None:
            skipped_window += 1
            continue

        row = {
            "pivot_time":    p["pivot_time"],
            "confirm_time":  p["confirm_time"],
            "label":         p["label"],
            "is_high":       is_high,
            "pivot_price":   p["price"],
            "entry_px":      entry_px,
            "confirm_lag":   p["confirm_lag_bars"],
            "bars_since_prev": p["bars_since_prev"],
            **{k: df[k].iloc[ci] for k in KEEP},
            **fwd,
        }
        # Good/bad label
        row["hits_target"] = fwd["mfe_pips"] >= TARGET_PIPS
        row["hits_stop"]   = fwd["mae_pips"] >= STOP_PIPS
        # Target hit BEFORE stop = a "good" pivot.
        # We need the order of events, not just whether both happened.
        # Walk the window to find first-hit order.
        good = False
        end = min(ci + LOOKAHEAD_BARS, len(df) - 1)
        for j in range(ci+1, end+1):
            hh = df["high"].iloc[j]; ll = df["low"].iloc[j]
            if is_high:                                # SELL
                hit_tgt = (entry_px - ll) / PIP >= TARGET_PIPS
                hit_stp = (hh - entry_px) / PIP >= STOP_PIPS
            else:                                      # BUY
                hit_tgt = (hh - entry_px) / PIP >= TARGET_PIPS
                hit_stp = (entry_px - ll) / PIP >= STOP_PIPS
            if hit_tgt and not hit_stp:
                good = True; break
            if hit_stp and not hit_tgt:
                good = False; break
            if hit_tgt and hit_stp:
                # Both within same bar — conservative: count as bad (worst-case fill)
                good = False; break
        row["good"] = good
        rows.append(row)

    fpiv = pd.DataFrame(rows)
    print(f"  built {len(fpiv):,} pivot feature rows  "
          f"(skipped {skipped_lookup} no-bar, {skipped_window} no-window)")

    fpiv.to_csv(OUT_PIV, index=False)
    print(f"saved → {OUT_PIV}")

    # ── Random control sample ────────────────────────────────────────
    print("\nbuilding random control sample...")
    rng = np.random.default_rng(RNG_SEED)
    pivot_confirm_set = set(piv["confirm_time"].astype("int64"))   # as ns timestamps
    # Sample 5x as many bars as pivots, excluding pivot confirm bars
    n_target = len(fpiv) * 5
    all_bars = df.index
    candidates = all_bars[
        (all_bars >= all_bars[200]) &                  # past warm-up
        (all_bars <= all_bars[-LOOKAHEAD_BARS-1])      # space for forward window
    ]
    sample_idx = rng.choice(len(candidates), size=min(n_target, len(candidates)), replace=False)
    sample_times = candidates[sample_idx]

    rnd_rows = []
    for t in sample_times:
        if t.value in pivot_confirm_set:               # skip if accidentally a pivot confirm
            continue
        ci = int(bar_idx.loc[t])
        entry_px = df["close"].iloc[ci]
        # For randoms, also compute MFE/MAE in both directions
        end = min(ci + LOOKAHEAD_BARS, len(df) - 1)
        window = df.iloc[ci+1:end+1]
        mfe_up   = (window["high"].max() - entry_px) / PIP
        mae_dn   = (entry_px - window["low"].min())  / PIP
        rnd_rows.append({
            "time": t,
            "entry_px": entry_px,
            "mfe_up_pips": mfe_up,
            "mae_dn_pips": mae_dn,
            **{k: df[k].iloc[ci] for k in KEEP},
        })

    frnd = pd.DataFrame(rnd_rows)
    print(f"  built {len(frnd):,} random feature rows")
    frnd.to_csv(OUT_RND, index=False)
    print(f"saved → {OUT_RND}")

    # Quick split summary
    print("\n── Pivot quality summary ──")
    print(f"good %:    {100*fpiv['good'].mean():.1f}")
    print(f"hits_target %: {100*fpiv['hits_target'].mean():.1f}")
    print(f"hits_stop %:   {100*fpiv['hits_stop'].mean():.1f}")
    print("\nby label:")
    summary = fpiv.groupby("label").agg(
        n=("good", "size"),
        good_pct=("good", lambda x: 100 * x.mean()),
        mfe_avg=("mfe_pips", "mean"),
        mae_avg=("mae_pips", "mean"),
    ).round(1)
    print(summary)


if __name__ == "__main__":
    main()
