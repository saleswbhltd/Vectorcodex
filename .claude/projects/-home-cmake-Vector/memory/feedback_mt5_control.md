---
name: mt5-terminal-control-rule
description: Hard rule — only kill/control terminal F1138FAFA5BD40AC6E39B58188E4EE88, never use blanket taskkill on terminal64.exe which would kill all 3 MT5 instances
metadata:
  type: feedback
---

Only ever kill or control the specific MT5 terminal: **F1138FAFA5BD40AC6E39B58188E4EE88**

**Why:** User runs 3 MT5 instances simultaneously. `taskkill /F /IM terminal64.exe` kills ALL of them. This caused unintended termination of other terminals during VECTOR003 testing on 2026-06-05.

**How to apply:**
- Use `mt5_control.py kill` which finds the correct PID via WMIC before killing
- If PID cannot be identified, the script refuses to kill anything (safe fallback)
- Never use `taskkill /IM terminal64.exe` directly
- The correct terminal exe is: `C:\Program Files\Roboforex 3 MT5 Terminal\terminal64.exe`
- Its data directory is: `C:\Users\cmake\AppData\Roaming\MetaQuotes\Terminal\F1138FAFA5BD40AC6E39B58188E4EE88\`
- The other two terminals must never be touched without explicit user permission
