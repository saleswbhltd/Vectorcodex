"""
sim_engine.py — Reusable causal backsim primitives for EURUSD M5 pivot strategies.

Key design rules enforced here:
  - Cooldown is FIRST-WINS (causal): no retroactive prob-replacement within the window.
    Non-causal replacement inflated WR by ~10pp in the VECTOR003 research — do not use it.
  - Trail logic: SL is checked BEFORE trail update on each bar (realistic: you exit on the
    low of the bar that triggers the stop, not the updated trail level).
  - Market entry: close of signal bar + spread. No look-ahead into next bar's open.

Usage:
    from sim_engine import (
        run_market_order, run_limit_order,
        dedupe_firstwins, collect_signals,
        report_subset, POINT, PIP,
    )
"""

import numpy as np
import pandas as pd

POINT = 0.00001
PIP   = 10 * POINT

# ── Defaults (override per-call) ──────────────────────────────────────────────
DEFAULT_SL_PIPS    = 5
DEFAULT_TRAIL_PIPS = 5
DEFAULT_TIME_STOP  = 12   # bars
DEFAULT_THR        = 0.70
DEFAULT_LOCAL_N    = 3
DEFAULT_CD_MIN     = 30


# ── Cooldown ──────────────────────────────────────────────────────────────────

def dedupe_firstwins(signals: pd.DataFrame, cooldown_min: int = DEFAULT_CD_MIN,
                     time_col: str = "candidate_time") -> pd.DataFrame:
    """
    Causal cooldown: first signal in each window wins.
    Never replaces a signal with a higher-prob later arrival — that's look-ahead.

    signals must have columns: `time_col`, `side`, `prob`.
    Global cooldown (BUY and SELL share the same window) unless you call this
    separately per side.
    """
    if signals.empty:
        return signals
    s = signals.sort_values(time_col).copy()
    keep = []; last_t = None
    for _, r in s.iterrows():
        t = r[time_col]
        if last_t is None or (t - last_t).total_seconds() >= cooldown_min * 60:
            keep.append(r)
            last_t = t
    return pd.DataFrame(keep)


def dedupe_firstwins_per_side(signals: pd.DataFrame, cooldown_min: int = DEFAULT_CD_MIN,
                               time_col: str = "candidate_time") -> pd.DataFrame:
    """
    Per-direction causal cooldown: BUY and SELL have independent 30-min clocks.
    Matches the EA's implementation in VECTOR003 v2.31.
    """
    if signals.empty:
        return signals
    s = signals.sort_values(time_col).copy()
    last_buy = last_sell = None
    keep = []
    for _, r in s.iterrows():
        t = r[time_col]
        side = r["side"]
        last_t = last_buy if side == "BUY" else last_sell
        if last_t is None or (t - last_t).total_seconds() >= cooldown_min * 60:
            keep.append(r)
            if side == "BUY":
                last_buy = t
            else:
                last_sell = t
    return pd.DataFrame(keep)


# ── Local-N gate + signal collection ─────────────────────────────────────────

def collect_signals(oos_panel: pd.DataFrame, score_max: np.ndarray,
                    best_side: np.ndarray,
                    thr: float = DEFAULT_THR,
                    local_n: int = DEFAULT_LOCAL_N) -> pd.DataFrame:
    """
    Apply threshold + local-N gate and return a DataFrame of candidate signals.

    score_max  : (n,) array of best-class GBM probabilities per bar
    best_side  : (n,) array of "BUY" or "SELL" per bar
    """
    high_arr = oos_panel["high"].values
    low_arr  = oos_panel["low"].values
    roll_max = pd.Series(high_arr).rolling(local_n, min_periods=1).max().values
    roll_min = pd.Series(low_arr).rolling(local_n, min_periods=1).min().values
    is_local_high = high_arr >= roll_max - POINT
    is_local_low  = low_arr  <= roll_min + POINT

    mask = score_max >= thr
    rows = []
    for i in np.where(mask)[0]:
        side = best_side[i]
        if side == "SELL" and not is_local_high[i]:
            continue
        if side == "BUY" and not is_local_low[i]:
            continue
        rows.append({
            "candidate_time": oos_panel.index[i],
            "side":  side,
            "prob":  float(score_max[i]),
            "limit": float(high_arr[i] if side == "SELL" else low_arr[i]),
        })
    return pd.DataFrame(rows)


# ── Market-order simulation ───────────────────────────────────────────────────

def run_market_order(panel: pd.DataFrame, sigs: pd.DataFrame,
                     spread_pips: float = 1.0,
                     sl_pips: int = DEFAULT_SL_PIPS,
                     trail_pips: int = DEFAULT_TRAIL_PIPS,
                     time_stop: int = DEFAULT_TIME_STOP,
                     time_col: str = "candidate_time") -> pd.DataFrame:
    """
    Market entry at close of signal bar (+ spread).

    Trail: SL ratchets up when price moves in favour. Checked order per bar:
      1. Did price hit current SL? → exit at SL
      2. Did price make new peak? → advance trail
    This means the SL level that catches the exit is always the level *before*
    the peak update on that same bar (conservative, matches real execution).
    """
    pidx = pd.Series(range(len(panel)), index=panel.index)
    results = []
    for _, s in sigs.iterrows():
        ts = s[time_col]
        if ts not in pidx.index:
            continue
        i = int(pidx.loc[ts])
        if i + 1 >= len(panel):
            continue
        side  = s["side"]
        entry = float(panel["close"].iloc[i])
        end_i = min(i + time_stop, len(panel) - 1)

        if side == "BUY":
            entry   += spread_pips * PIP
            sl_price = entry - sl_pips * PIP
            peak     = entry
            pnl      = None
            for j in range(i + 1, end_i + 1):
                h  = float(panel["high"].iloc[j])
                lo = float(panel["low"].iloc[j])
                if lo <= sl_price:
                    pnl = (sl_price - entry) / PIP; break
                if h > peak:
                    peak = h
                    new_sl = peak - trail_pips * PIP
                    if new_sl > sl_price:
                        sl_price = new_sl
            if pnl is None:
                pnl = (float(panel["close"].iloc[end_i]) - entry) / PIP
        else:  # SELL
            entry   -= spread_pips * PIP
            sl_price = entry + sl_pips * PIP
            peak     = entry
            pnl      = None
            for j in range(i + 1, end_i + 1):
                h  = float(panel["high"].iloc[j])
                lo = float(panel["low"].iloc[j])
                if h >= sl_price:
                    pnl = (entry - sl_price) / PIP; break
                if lo < peak:
                    peak = lo
                    new_sl = peak + trail_pips * PIP
                    if new_sl < sl_price:
                        sl_price = new_sl
            if pnl is None:
                pnl = (entry - float(panel["close"].iloc[end_i])) / PIP

        results.append({"pnl": pnl, "side": side, "win": pnl > 0, "filled": True})
    return pd.DataFrame(results)


# ── Limit-order simulation ────────────────────────────────────────────────────

DEFAULT_LIMIT_EXPIRY = 6   # bars

def run_limit_order(panel: pd.DataFrame, sigs: pd.DataFrame,
                    spread_pips: float = 1.0,
                    buffer_pips: float = 0.0,
                    sl_pips: int = DEFAULT_SL_PIPS,
                    trail_pips: int = DEFAULT_TRAIL_PIPS,
                    time_stop: int = DEFAULT_TIME_STOP,
                    expiry_bars: int = DEFAULT_LIMIT_EXPIRY,
                    time_col: str = "candidate_time") -> pd.DataFrame:
    """
    Limit entry at bar's extreme ± buffer_pips. Unfilled rows have filled=False.
    """
    pidx = pd.Series(range(len(panel)), index=panel.index)
    results = []
    for _, s in sigs.iterrows():
        ts = s[time_col]
        if ts not in pidx.index:
            continue
        i = int(pidx.loc[ts])
        limit = float(s["limit"])
        side  = s["side"]
        if side == "SELL":
            limit -= buffer_pips * PIP
        else:
            limit += buffer_pips * PIP

        fill_idx = None
        for k in range(1, expiry_bars + 1):
            j = i + k
            if j >= len(panel):
                break
            if side == "SELL" and panel["high"].iloc[j] >= limit:
                fill_idx = j; break
            if side == "BUY"  and panel["low"].iloc[j]  <= limit:
                fill_idx = j; break

        if fill_idx is None:
            results.append({"pnl": None, "side": side, "win": False, "filled": False})
            continue

        entry = limit - (spread_pips * PIP if side == "SELL" else -spread_pips * PIP)
        end_i = min(fill_idx + time_stop, len(panel) - 1)

        if side == "BUY":
            sl_price = entry - sl_pips * PIP; peak = entry; pnl = None
            for j in range(fill_idx + 1, end_i + 1):
                h  = float(panel["high"].iloc[j])
                lo = float(panel["low"].iloc[j])
                if lo <= sl_price:
                    pnl = (sl_price - entry) / PIP; break
                if h > peak:
                    peak = h
                    new_sl = peak - trail_pips * PIP
                    if new_sl > sl_price:
                        sl_price = new_sl
            if pnl is None:
                pnl = (float(panel["close"].iloc[end_i]) - entry) / PIP
        else:
            sl_price = entry + sl_pips * PIP; peak = entry; pnl = None
            for j in range(fill_idx + 1, end_i + 1):
                h  = float(panel["high"].iloc[j])
                lo = float(panel["low"].iloc[j])
                if h >= sl_price:
                    pnl = (entry - sl_price) / PIP; break
                if lo < peak:
                    peak = lo
                    new_sl = peak + trail_pips * PIP
                    if new_sl < sl_price:
                        sl_price = new_sl
            if pnl is None:
                pnl = (entry - float(panel["close"].iloc[end_i])) / PIP

        results.append({"pnl": pnl, "side": side, "win": pnl > 0, "filled": True})
    return pd.DataFrame(results)


# ── Reporting ─────────────────────────────────────────────────────────────────

def report_subset(label: str, trades: pd.DataFrame, n_signals: int,
                  oos_days: float = 30.0):
    """Print one-line P&L summary. oos_days used for per-month scaling."""
    if trades.empty:
        print(f"  {label:40s}  no trades")
        return
    filled = trades[trades.get("filled", pd.Series(True, index=trades.index))]
    if filled.empty:
        print(f"  {label:40s}  no fills  (signals={n_signals})")
        return
    wins  = filled["pnl"] > 0
    wr    = 100 * wins.mean()
    edge  = filled["pnl"].mean()
    total = filled["pnl"].sum()
    mo    = total * (30 / oos_days)
    buy_df  = filled[filled["side"] == "BUY"]
    sell_df = filled[filled["side"] == "SELL"]
    bwr = f"{100*buy_df['pnl'].gt(0).mean():.1f}%" if not buy_df.empty else "n/a"
    swr = f"{100*sell_df['pnl'].gt(0).mean():.1f}%" if not sell_df.empty else "n/a"
    print(f"  {label:40s}  sigs={n_signals:>4d}  trades={len(filled):>4d}  "
          f"WR={wr:>5.1f}%  edge={edge:>+5.2f}p  P&L/mo={mo:>+5.0f}p  "
          f"BUY_WR={bwr}  SELL_WR={swr}")
