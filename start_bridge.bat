@echo off
REM start_bridge.bat — launch VECTOR003 Python bridge (Windows-native).
REM Uses pythonw.exe from the PycharmProjects venv (no console window).
REM Bridge itself enforces single-instance, so calling when one is already up is harmless.

set "BRIDGE_PY=C:\Users\cmake\PycharmProjects\PythonProject\VECTOR003_BRIDGE.py"
set "PYW=C:\Users\cmake\PycharmProjects\PythonProject\.venv310\Scripts\pythonw.exe"

if not exist "%PYW%" (
    echo [start_bridge] pythonw not found at %PYW%
    exit /b 1
)
if not exist "%BRIDGE_PY%" (
    echo [start_bridge] bridge script not found at %BRIDGE_PY%
    exit /b 1
)

start "VECTOR003 Bridge" /B "%PYW%" "%BRIDGE_PY%"
exit /b 0
