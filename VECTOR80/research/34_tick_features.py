"""
Step 34 — Build tick-level features per M5 bar.

For each M5 bar, computes features derived from ALL ticks within that bar
that capture intra-bar dynamics the bar's OHLC smooths away:

  tick_count                 — number of ticks (already in resampled OHLC)
  median_tick_interval_ms    — typical pace (lower = busier bar)
  max_tick_interval_ms       — longest gap (liquidity withdrawal)
  spread_avg / spread_max    — bid-ask spread mean / peak
  tick_velocity_first_half   — abs(mid_change) per tick, first half of bar
  tick_velocity_second_half  — same, second half (deceleration?)
  vel_ratio_2nd_to_1st       — second half / first half (≪1 = decelerating)
  bid_aggressor_pct          — % of ticks where bid moved up (aggressive buying)
  ask_aggressor_pct          — % of ticks where ask moved down (aggressive selling)
  imbalance                  — bid_aggressor - ask_aggressor
  max_run_up_pips_intrabar   — biggest up-move within the bar
  max_run_dn_pips_intrabar   — biggest down-move within the bar
  reversal_strength          — abs(open-close) / max(intra_run_up, intra_run_dn)
  ticks_at_high_pct          — % of ticks within 1 pip of bar's high
  ticks_at_low_pct           — % of ticks within 1 pip of bar's low
  near_high_then_low         — ticks at high precede ticks at low? (top → drop signature)

These features attempt to identify EXHAUSTION at the extreme within the bar —
the actual pivot dynamic that bar-level RSI/BB cannot see.
"""

import pandas as pd
import numpy as np

TICK_SRC = "/home/cmake/Vector/research/EURUSD_TICK_dukascopy_2025_2026.csv.gz"
M5_SRC   = "/home/cmake/Vector/research/EURUSD_M5_dukascopy_2025_2026.csv.gz"
OUT      = "/home/cmake/Vector/research/EURUSD_M5_tick_features.csv.gz"
PIP      = 0.0001


def main():
    print("loading ticks (compressed)...")
    ticks = pd.read_csv(TICK_SRC, parse_dates=["datetime"])
    ticks["datetime"] = pd.to_datetime(ticks["datetime"], utc=True, format="ISO8601").dt.tz_localize(None)
    ticks = ticks.sort_values("datetime").reset_index(drop=True)
    print(f"  ticks: {len(ticks):,}")

    print("loading M5 bars...")
    m5 = pd.read_csv(M5_SRC, parse_dates=["datetime"])
    m5["datetime"] = pd.to_datetime(m5["datetime"], utc=True, format="ISO8601").dt.tz_localize(None)
    m5 = m5.set_index("datetime").sort_index()
    print(f"  bars: {len(m5):,}")

    # Tick-level derived quantities
    ticks["mid_change_pips"] = ticks["mid"].diff().abs() / PIP
    ticks["spread_pips"]     = (ticks["ask"] - ticks["bid"]) / PIP
    ticks["bid_change"]      = ticks["bid"].diff()
    ticks["ask_change"]      = ticks["ask"].diff()
    ticks["bid_up"]   = (ticks["bid_change"] > 0).astype(int)
    ticks["ask_down"] = (ticks["ask_change"] < 0).astype(int)
    ticks["time_delta_ms"]   = ticks["datetime"].diff().dt.total_seconds() * 1000
    # Assign each tick to the M5 bar it belongs to
    ticks["bar_time"] = ticks["datetime"].dt.floor("5min")

    print(f"\nGrouping by M5 bar ({ticks['bar_time'].nunique():,} unique bars)...")

    # Per-bar aggregations using groupby
    g = ticks.groupby("bar_time", sort=False)

    feats = pd.DataFrame(index=g.size().index)
    feats["tick_count"]              = g.size()
    feats["median_tick_interval_ms"] = g["time_delta_ms"].median()
    feats["max_tick_interval_ms"]    = g["time_delta_ms"].max()
    feats["spread_avg"]              = g["spread_pips"].mean()
    feats["spread_max"]              = g["spread_pips"].max()
    feats["bid_aggressor_pct"]       = 100 * g["bid_up"].mean()
    feats["ask_aggressor_pct"]       = 100 * g["ask_down"].mean()
    feats["imbalance"]               = feats["bid_aggressor_pct"] - feats["ask_aggressor_pct"]

    # Per-bar high/low and intra-bar movement
    feats["bar_high"] = g["mid"].max()
    feats["bar_low"]  = g["mid"].min()

    # For each bar: split into first/second half and compare velocity
    def half_split_velocity(group):
        n = len(group)
        if n < 4: return pd.Series({"vel1": np.nan, "vel2": np.nan,
                                     "run_up": np.nan, "run_dn": np.nan,
                                     "at_high_pct": np.nan, "at_low_pct": np.nan})
        half = n // 2
        v1 = group["mid_change_pips"].iloc[:half].sum() / half
        v2 = group["mid_change_pips"].iloc[half:].sum() / (n - half)
        # max run-up = max(cummax(mid) - mid_start) ; cumulative growth from start
        mid = group["mid"].values
        cummax = np.maximum.accumulate(mid)
        cummin = np.minimum.accumulate(mid)
        run_up = (cummax - cummin[0]) / PIP if len(mid) else np.nan
        run_dn = (cummax[0] - cummin) / PIP if len(mid) else np.nan
        run_up_max = float(np.max(run_up)) if len(mid) else np.nan
        run_dn_max = float(np.max(run_dn)) if len(mid) else np.nan
        # Where is the high in the bar? At the start, middle, or end?
        h = group["mid"].max(); l = group["mid"].min()
        near_h = ((h - group["mid"]) / PIP <= 1.0).mean() * 100
        near_l = ((group["mid"] - l) / PIP <= 1.0).mean() * 100
        return pd.Series({"vel1": v1, "vel2": v2,
                          "run_up": run_up_max, "run_dn": run_dn_max,
                          "at_high_pct": near_h, "at_low_pct": near_l})

    print("Per-bar velocity profile (slow — iterates groups)...")
    velocity_df = g.apply(half_split_velocity, include_groups=False)
    if velocity_df.empty:
        print("WARNING: velocity_df empty")
    else:
        feats["tick_velocity_first_half"]  = velocity_df["vel1"]
        feats["tick_velocity_second_half"] = velocity_df["vel2"]
        feats["vel_ratio_2nd_to_1st"]      = velocity_df["vel2"] / velocity_df["vel1"].replace(0, np.nan)
        feats["max_run_up_pips_intrabar"]  = velocity_df["run_up"]
        feats["max_run_dn_pips_intrabar"]  = velocity_df["run_dn"]
        feats["ticks_at_high_pct"]         = velocity_df["at_high_pct"]
        feats["ticks_at_low_pct"]          = velocity_df["at_low_pct"]

    # Join with M5 OHLC
    out = m5.join(feats, how="left")
    print(f"\nJoined features: {len(out):,} bars × {len(out.columns)} cols")
    print("Sample columns:", list(out.columns[-12:]))
    out.to_csv(OUT, compression="gzip", float_format="%.4f")
    print(f"saved → {OUT}")


if __name__ == "__main__":
    main()
