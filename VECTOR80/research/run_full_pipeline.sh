#!/bin/bash
# After all 3 tick downloads complete, run this to:
#   1. Concatenate ticks → M5/M1 OHLC
#   2. Build per-M5-bar tick features
#   3. Build full panel (M5 indicators + tick features + H1)
#   4. Run final GBM comparison (M5+H1 baseline vs +TICK)
#
# Usage: bash /home/cmake/Vector/research/run_full_pipeline.sh

set -e
cd /home/cmake/Vector/research

echo "═══════════════════════════════════════════════════════"
echo " VECTOR — Full tick pipeline"
echo "═══════════════════════════════════════════════════════"

echo
echo "[33/4] Concatenating ticks + resampling to M5/M1..."
python3 33_ticks_to_ohlc.py

echo
echo "[34/4] Building per-bar tick features..."
python3 34_tick_features.py

echo
echo "[35/4] Building full panel (M5 indicators + ticks + H1)..."
python3 35_build_full_panel.py

echo
echo "[36/4] Running per-type GBM comparison..."
python3 36_final_gbm_with_ticks.py

echo
echo "═══════════════════════════════════════════════════════"
echo " DONE. Results: /home/cmake/Vector/research/final_gbm_results.csv"
echo "═══════════════════════════════════════════════════════"
