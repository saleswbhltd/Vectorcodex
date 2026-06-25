#!/bin/bash
# deploy_v3.sh — Deploy VECTOR003 EA + .set to one or all known MT5 terminals
#
# Usage:
#   bash deploy_v3.sh                # deploy to all known terminals
#   bash deploy_v3.sh <terminal_id>  # deploy to specific terminal

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Vector project terminal ONLY — do NOT add others (5FFA and 72B4 belong to other projects)
TERMINALS=(
    "F1138FAFA5BD40AC6E39B58188E4EE88"
)

# If user supplied an ID, use only that one
if [ -n "$1" ]; then
    TERMINALS=("$1")
fi

# Generate the .set file once (UTF-16 LE with BOM)
SET_PATH=$(mktemp)
python3 - "$SET_PATH" <<'PY'
import sys
content = """; VECTOR003 — MODERATE preset
; Validated on 14 months of EURUSD M5 (walk-forward, 11/11 profitable months)
;
InpRiskPct=0.5||0.5||0.1||3.0||N
InpMaxOpenTrades=4||4||1||10||N
InpMagic=20030001||20030001||1||20030010||N
InpThreshold=0.70||0.70||0.05||0.95||N
InpCooldownMin=30||30||5||120||N
InpLocalN=3||3||1||10||N
InpSLPips=5.0||5.0||0.5||20.0||N
InpTrailPips=5.0||5.0||0.5||20.0||N
InpTimeoutMin=60||60||5||240||N
InpBridgeTimeoutMs=3000||3000||100||10000||N
InpDrawArrows=true
InpShowPanel=true
"""
with open(sys.argv[1], "wb") as f:
    f.write(b"\xff\xfe")
    f.write(content.replace("\n", "\r\n").encode("utf-16-le"))
PY

echo "=== Deploying VECTOR003 ==="

for TID in "${TERMINALS[@]}"; do
    BASE="/mnt/c/Users/cmake/AppData/Roaming/MetaQuotes/Terminal/$TID"
    if [ ! -d "$BASE" ]; then
        echo "  SKIP $TID (directory not found)"
        continue
    fi
    ADV="$BASE/MQL5/Experts/Advisors"
    SETD="$BASE/MQL5/Profiles/Tester"
    FILESD="$BASE/MQL5/Files"
    mkdir -p "$ADV" "$SETD" "$FILESD"

    cp "$SCRIPT_DIR/VECTOR003.mq5"      "$ADV/VECTOR003.mq5"
    cp "$SET_PATH"                       "$SETD/VECTOR003.set"
    cp "$SCRIPT_DIR/start_bridge.bat"   "$FILESD/start_bridge.bat"
    echo "  $TID:"
    echo "    EA   → $ADV/VECTOR003.mq5"
    echo "    set  → $SETD/VECTOR003.set"
    echo "    bat  → $FILESD/start_bridge.bat"
done

rm -f "$SET_PATH"

echo ""
echo "=== Sync Python bridge to PythonProject (Windows-native) ==="
PROJ="/mnt/c/Users/cmake/PycharmProjects/PythonProject"
if [ -d "$PROJ" ]; then
    cp "$SCRIPT_DIR/VECTOR003_BRIDGE.py" "$PROJ/VECTOR003_BRIDGE.py"
    mkdir -p "$PROJ/models"
    cp "$SCRIPT_DIR/models/"*.pkl       "$PROJ/models/" 2>/dev/null
    cp "$SCRIPT_DIR/models/manifest.json" "$PROJ/models/" 2>/dev/null
    n=$(ls -1 "$PROJ/models/"*.pkl 2>/dev/null | wc -l)
    echo "  bridge → $PROJ/VECTOR003_BRIDGE.py"
    echo "  models → $PROJ/models/   ($n pkl files)"
else
    echo "  SKIP: $PROJ not found"
fi

echo ""
echo "=== Next steps ==="
echo "1. In MT5 (both terminals), compile VECTOR003.mq5 (MetaEditor F4, then F7)"
echo "2. Attach VECTOR003 to EURUSD M5 (AutoTrading + 'Allow DLL imports' ON)"
echo "3. EA will auto-launch the bridge via start_bridge.bat"
echo "4. Watch on-chart panel — 'bridge OK' = ready, 'BRIDGE DOWN' = paused"
echo "Done."
