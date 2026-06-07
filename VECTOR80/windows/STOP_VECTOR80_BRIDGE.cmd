@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Stop-ScheduledTask -TaskName 'VECTOR80 Bridge Supervisor' -ErrorAction SilentlyContinue; Disable-ScheduledTask -TaskName 'VECTOR80 Bridge Supervisor' -ErrorAction SilentlyContinue | Out-Null"
wsl.exe -d Ubuntu -- bash -lc "pkill -f 'vector80_live_bridge.py' || true"
echo VECTOR80 bridge stopped and automatic restart disabled.
pause
