#!/bin/bash
# start_bridge.sh — launch VECTOR003 Python bridge as a detached background process.
# Called from start_bridge.bat -> wsl.exe.  Survives the caller's exit via setsid+nohup.
cd /home/cmake/Vector
setsid nohup python3 /home/cmake/Vector/VECTOR003_BRIDGE.py \
    >> /home/cmake/Vector/bridge.out 2>&1 < /dev/null &
disown
exit 0
