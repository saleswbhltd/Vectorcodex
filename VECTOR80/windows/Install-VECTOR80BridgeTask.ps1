$ErrorActionPreference = "Stop"

$TaskName = "VECTOR80 Bridge Supervisor"
$InstallDir = Join-Path $env:LOCALAPPDATA "VECTOR80"
$Supervisor = Join-Path $InstallDir "VECTOR80_BridgeSupervisor.ps1"
$PowerShell = (Get-Command powershell.exe).Source
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
$SupervisorSource = Join-Path $PSScriptRoot "VECTOR80_BridgeSupervisor.ps1"
if ([IO.Path]::GetFullPath($SupervisorSource) -ne [IO.Path]::GetFullPath($Supervisor)) {
    Copy-Item -Path $SupervisorSource -Destination $Supervisor -Force
}

$Action = New-ScheduledTaskAction `
    -Execute $PowerShell `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$Supervisor`""
$Trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Description "Keeps the VECTOR80 Python scoring bridge running whenever MT5 is open." `
    -Force | Out-Null

Start-ScheduledTask -TaskName $TaskName
Write-Host "Installed and started: $TaskName"
