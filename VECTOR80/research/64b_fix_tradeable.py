"""
Step 64b — Fix the MAE=0 bug in tradeable labeling.

Pivots with MAE=0 are PERFECT entries (no drawdown) and should always be
tradeable if MFE meets the minimum. The previous condition `a > 0 and m/a >= rr`
incorrectly marked these as NOT tradeable.

Correct rule:
  tradeable = (MFE ≥ mfe_min) AND
              ( (MAE == 0) OR (MFE/MAE ≥ rr) ) AND
              ( MFE first-hit valid ) AND
              ( MAE not hit before MFE )
"""

import pandas as pd
import numpy as np

V3_DEV = "/home/cmake/Vector/research/pivot_map_v3.csv"
V3_OOS = "/home/cmake/Vector/research/pivot_map_v3_oos.csv"

MFE_MIN = 8.0
RR_MIN  = 3.0


def relabel(path):
    df = pd.read_csv(path)
    def is_tradeable(r):
        mfe = r["mfe_60m"]; mae = r["mae_60m"]
        m_hit = r["mfe_first_hit"]; a_hit = r["mae_first_hit"]
        if pd.isna(mfe) or mfe < MFE_MIN: return False
        if pd.isna(m_hit): return False           # MFE never crossed mfe_min
        if pd.notna(a_hit) and a_hit <= m_hit: return False  # MAE hit first
        # R:R check (special-case MAE == 0 → infinite ratio → always pass)
        if mae > 0 and (mfe / mae) < RR_MIN: return False
        return True
    df["tradeable"] = df.apply(is_tradeable, axis=1)
    return df


for path in (V3_DEV, V3_OOS):
    df = relabel(path)
    n_t = int(df["tradeable"].sum())
    n_all = len(df)
    days = (pd.to_datetime(df["pivot_time"]).max() - pd.to_datetime(df["pivot_time"]).min()).days
    print(f"{path}")
    print(f"  total: {n_all}  tradeable: {n_t} ({100*n_t/n_all:.1f}%)  "
          f"{n_t/max(days,1):.1f}/day ≈ {n_t/max(days,1)*30:.0f}/month")
    df.to_csv(path, index=False, float_format="%.5f")
print("done.")
