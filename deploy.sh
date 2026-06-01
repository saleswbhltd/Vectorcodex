#!/bin/bash
# deploy.sh — copy VECTOR001 EA to MT5
# Source: /home/cmake/Vector/
# Target: MQL5\Experts\Advisors\

MT5_ADVISORS="/mnt/c/Users/cmake/AppData/Roaming/MetaQuotes/Terminal/5FFA568149E88FCD5B44D926DCFEAA79/MQL5/Experts/Advisors"

cp VECTOR001.mq5 "$MT5_ADVISORS/VECTOR001.mq5" && echo "VECTOR001.mq5 deployed to Advisors/"
