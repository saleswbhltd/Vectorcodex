$ErrorActionPreference = "Continue"

$Distro = "Ubuntu"
$BridgeCommand = "cd /home/cmake/Vectorcodex/VECTOR80 && exec nice -n 10 taskset -c 0,1 python3 scripts/vector80_live_bridge.py"
$Log = Join-Path $env:LOCALAPPDATA "VECTOR80\bridge-supervisor.log"
$LogDir = Split-Path $Log
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Write-BridgeLog([string]$Message) {
    "$(Get-Date -Format s) $Message" | Add-Content -Path $Log
}

Write-BridgeLog "supervisor started"
while ($true) {
    $mt5 = Get-Process -Name "terminal64" -ErrorAction SilentlyContinue
    if (-not $mt5) {
        Start-Sleep -Seconds 2
        continue
    }

    Write-BridgeLog "MT5 detected; starting Python bridge"
    & wsl.exe -d $Distro -- bash -lc $BridgeCommand
    $exitCode = $LASTEXITCODE
    Write-BridgeLog "bridge exited code=$exitCode; restart in 5 seconds"
    Start-Sleep -Seconds 5
}
