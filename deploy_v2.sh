#!/bin/bash
# deploy_v2.sh — copy VECTOR002 EA to MT5

MT5_ADVISORS="/mnt/c/Users/cmake/AppData/Roaming/MetaQuotes/Terminal/5FFA568149E88FCD5B44D926DCFEAA79/MQL5/Experts/Advisors"

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cp "$SCRIPT_DIR/VECTOR002.mq5" "$MT5_ADVISORS/VECTOR002.mq5" && echo "VECTOR002.mq5 deployed to Advisors/"
