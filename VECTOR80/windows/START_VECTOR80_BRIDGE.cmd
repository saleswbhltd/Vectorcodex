@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Enable-ScheduledTask -TaskName 'VECTOR80 Bridge Supervisor' -ErrorAction Stop | Out-Null; Start-ScheduledTask -TaskName 'VECTOR80 Bridge Supervisor' -ErrorAction Stop"
echo VECTOR80 low-power bridge supervisor enabled and started.
pause
