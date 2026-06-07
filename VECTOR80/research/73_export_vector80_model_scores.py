#!/usr/bin/env python3
"""
Export VECTOR80 validated research scores for the MT5 prototype EA.

The EA reads Common Files/VECTOR80_model_scores.csv with:
  time,engine_id,score

This exporter uses the deduped SELL-expanded OOS signal file produced by the
research pipeline. It is for prototype/backtest replay of the validated OOS
signals, not live inference.
"""

from pathlib import Path

import pandas as pd


BASE = Path("/home/cmake/Vector/research")
SRC = BASE / "zzlines_code_ready_sell_expanded_oos_signals.csv"
OUT = BASE / "VECTOR80_model_scores.csv"


def main() -> None:
    signals = pd.read_csv(SRC, parse_dates=["entry_time"])
    required = {"entry_time", "engine_id", "score"}
    missing = required - set(signals.columns)
    if missing:
        raise SystemExit(f"missing required columns: {sorted(missing)}")

    out = signals.loc[:, ["entry_time", "engine_id", "score"]].copy()
    out = out.rename(columns={"entry_time": "time"})
    out["time"] = out["time"].dt.strftime("%Y-%m-%d %H:%M:%S")
    out = out.sort_values(["time", "engine_id"]).drop_duplicates(["time", "engine_id"], keep="last")
    out.to_csv(OUT, index=False, float_format="%.6f")

    print(f"exported {len(out)} score rows -> {OUT}")


if __name__ == "__main__":
    main()
