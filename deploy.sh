#!/bin/bash
# deploy.sh — copy VECTOR001 EA to MT5
# Source: /home/cmake/Vector/
# Target: MQL5\Experts\Advisors\

MT5_ADVISORS="/mnt/c/Users/cmake/AppData/Roaming/MetaQuotes/Terminal/F1138FAFA5BD40AC6E39B58188E4EE88/MQL5/Experts/Advisors"

cp VECTOR001.mq5 "$MT5_ADVISORS/VECTOR001.mq5" && echo "VECTOR001.mq5 deployed to Advisors/"
