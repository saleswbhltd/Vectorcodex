#!/bin/bash
# run_backtest.sh — Automated VECTOR003 Strategy Tester pipeline
#
# Usage:
#   bash run_backtest.sh                              # default: Apr 30 – Jun 4 2026, real ticks
#   bash run_backtest.sh 2026.01.01 2026.04.01       # custom date range
#   bash run_backtest.sh 2026.01.01 2026.04.01 my_tag  # custom dates + report tag
#
# What it does:
#   1. Writes tester config (dates, model, EA, symbol)
#   2. Gracefully closes our MT5 terminal (Roboforex 3 / F1138)
#   3. Relaunches terminal fresh — fresh launch honours /config and auto-starts tester
#      ShutdownTerminal=1 closes it automatically when done
#   4. Waits for the terminal process to exit (test complete)
#   5. Parses the HTML report, prints key metrics
#   6. Relaunches terminal normally for live monitoring

set -e

# ── Config ────────────────────────────────────────────────────────────────────
TERMINAL_EXE="C:\\Program Files\\Roboforex 3 MT5 Terminal\\terminal64.exe"
TERMINAL_DATA="F1138FAFA5BD40AC6E39B58188E4EE88"
DATA_DIR="/mnt/c/Users/cmake/AppData/Roaming/MetaQuotes/Terminal/$TERMINAL_DATA"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

FROM_DATE="${1:-2026.04.30}"
TO_DATE="${2:-2026.06.04}"
TAG="${3:-$(date +%Y%m%d_%H%M%S)}"
REPORT_NAME="VECTOR003_${TAG}"
REPORT_PATH="$DATA_DIR/${REPORT_NAME}.htm"
INI_PATH="$DATA_DIR/config/vector003_tester.ini"

echo "======================================================"
echo "  VECTOR003 Automated Backtest"
echo "  Period : $FROM_DATE → $TO_DATE"
echo "  Report : ${REPORT_NAME}.htm"
echo "======================================================"

# ── Step 1: Write tester config ───────────────────────────────────────────────
python3 - "$INI_PATH" "$FROM_DATE" "$TO_DATE" "$REPORT_NAME" <<'PY'
import sys

ini_path, from_date, to_date, report_name = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]

content = (
    "[Tester]\r\n"
    "Expert=Advisors\\VECTOR003\r\n"
    "ExpertParameters=VECTOR003.set\r\n"
    "Symbol=EURUSD\r\n"
    "Period=M5\r\n"
    "Model=4\r\n"          # 4 = Every tick based on real ticks
    "Optimization=0\r\n"
    f"FromDate={from_date}\r\n"
    f"ToDate={to_date}\r\n"
    "ForwardMode=0\r\n"
    "Deposit=10000\r\n"
    "Currency=USD\r\n"
    "Leverage=100\r\n"
    "ExecutionMode=0\r\n"
    f"Report={report_name}\r\n"
    "ShutdownTerminal=1\r\n"   # close terminal when test completes
)

with open(ini_path, "wb") as f:
    f.write(b"\xff\xfe")
    f.write(content.encode("utf-16-le"))

print(f"  Config written → {ini_path}")
PY

# ── Step 1b: Compile EA (ensure fresh .ex5 before tester runs) ───────────────
METAEDITOR="C:\\Program Files\\Roboforex 3 MT5 Terminal\\metaeditor64.exe"
MT5_EXPERTS="C:\\Users\\cmake\\AppData\\Roaming\\MetaQuotes\\Terminal\\$TERMINAL_DATA\\MQL5\\Experts\\Advisors"
COMPILE_LOG="/tmp/vector003_compile.log"

echo ""
echo "[0/4] Compiling VECTOR003.mq5..."
powershell.exe -Command \
  "& '$METAEDITOR' /compile:'$MT5_EXPERTS\\VECTOR003.mq5' /log:'C:\\Users\\cmake\\AppData\\Local\\Temp\\vector003_compile.log'" \
  2>/dev/null
sleep 5

# Read compile log from Windows temp
COMPILE_LOG_WIN="/mnt/c/Users/cmake/AppData/Local/Temp/vector003_compile.log"
if [ -f "$COMPILE_LOG_WIN" ]; then
    python3 -c "
import sys, codecs
try:
    with open('$COMPILE_LOG_WIN', 'rb') as f:
        raw = f.read()
    # Strip UTF-16 BOM if present
    if raw[:2] in (b'\\xff\\xfe', b'\\xfe\\xff'):
        txt = raw.decode('utf-16')
    else:
        txt = raw.decode('utf-8', errors='replace')
    print(txt.strip())
except Exception as e:
    print(f'  (could not read compile log: {e})')
" 2>/dev/null || true
fi

# Verify .ex5 is newer than .mq5
MQ5_TIME=$(stat -c %Y "$DATA_DIR/MQL5/Experts/Advisors/VECTOR003.mq5" 2>/dev/null || echo 0)
EX5_TIME=$(stat -c %Y "$DATA_DIR/MQL5/Experts/Advisors/VECTOR003.ex5" 2>/dev/null || echo 0)
if [ "$EX5_TIME" -ge "$MQ5_TIME" ]; then
    echo "  ✓ Compile OK — VECTOR003.ex5 is up to date"
else
    echo "  ✗ WARNING: .ex5 ($EX5_TIME) is still older than .mq5 ($MQ5_TIME) — compile may have failed"
    echo "  Aborting — fix compilation before running backtest"
    exit 1
fi

# ── Step 2: Find and gracefully close our terminal ────────────────────────────
echo ""
echo "[1/4] Closing Roboforex 3 terminal..."

OUR_PID=$(powershell.exe -Command \
  "Get-Process terminal64 -ErrorAction SilentlyContinue | Where-Object { \$_.MainModule.FileName -like '*Roboforex 3*' } | Select-Object -ExpandProperty Id" \
  2>/dev/null | tr -d '\r')

if [ -n "$OUR_PID" ]; then
    echo "  Found PID $OUR_PID — sending close signal..."
    powershell.exe -Command "Stop-Process -Id $OUR_PID -ErrorAction SilentlyContinue" 2>/dev/null
    sleep 4
    echo "  Terminal closed."
else
    echo "  Terminal not running — proceeding."
fi

# ── Step 3: Launch terminal fresh with tester config ─────────────────────────
echo ""
echo "[2/4] Launching terminal in tester mode..."

NEW_PID=$(powershell.exe -Command \
  "Start-Process '$TERMINAL_EXE' -ArgumentList '/config:C:\\Users\\cmake\\AppData\\Roaming\\MetaQuotes\\Terminal\\$TERMINAL_DATA\\config\\vector003_tester.ini' -PassThru | Select-Object -ExpandProperty Id" \
  2>/dev/null | tr -d '\r')

echo "  Started PID $NEW_PID — tester running..."
echo "  (Expected duration: 5–15 minutes for 35-day real-tick backtest)"
echo ""

# ── Step 4: Wait for terminal to exit (ShutdownTerminal=1) ───────────────────
echo "[3/4] Waiting for backtest to complete..."

ELAPSED=0
while powershell.exe -Command "Get-Process -Id $NEW_PID -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id" 2>/dev/null | grep -q "$NEW_PID"; do
    sleep 30
    ELAPSED=$((ELAPSED + 30))
    echo "  ...${ELAPSED}s elapsed — still running..."
    # Print bridge activity if any
    BRIDGE_SIZE=$(wc -c < "/mnt/c/Users/cmake/AppData/Roaming/MetaQuotes/Terminal/Common/Files/vector003_bridge.log" 2>/dev/null || echo 0)
    echo "  Bridge log: ${BRIDGE_SIZE} bytes"
done

echo "  Terminal exited — test complete."
echo ""

# ── Step 5: Parse report ──────────────────────────────────────────────────────
echo "[4/4] Parsing report..."

if [ -f "$REPORT_PATH" ]; then
    python3 "$SCRIPT_DIR/parse_report.py" "$REPORT_PATH"
else
    echo "  WARNING: Report not found at $REPORT_PATH"
    echo "  Available reports:"
    ls -lt "$DATA_DIR/"*.htm 2>/dev/null | head -5
fi

# ── Step 6: Relaunch terminal normally ────────────────────────────────────────
echo ""
echo "Relaunching terminal for live monitoring..."
powershell.exe -Command "Start-Process '$TERMINAL_EXE' -PassThru | Select-Object -ExpandProperty Id" 2>/dev/null | tr -d '\r' | xargs -I{} echo "  Terminal restarted (PID {})"

echo ""
echo "======================================================"
echo "  Done. Report saved: ${REPORT_NAME}.htm"
echo "======================================================"
