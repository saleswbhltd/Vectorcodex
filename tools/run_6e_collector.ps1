$ErrorActionPreference = 'Continue'
$python = 'C:\Users\cmake\PycharmProjects\PythonProject\.venv310\Scripts\python.exe'
$script = 'C:\Users\cmake\PycharmProjects\PythonProject\6EFutures.py'
$log = 'C:\Users\cmake\AppData\Local\VECTOR80\6e_collector.log'
Set-Location -LiteralPath (Split-Path -Parent $script)
$stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
$existing = Get-CimInstance Win32_Process -Filter "name='python.exe' or name='pythonw.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like '*6EFutures.py*' }
if ($existing) {
    Add-Content -LiteralPath $log -Value "[$stamp] collector already running; exiting"
    exit 0
}
Add-Content -LiteralPath $log -Value "[$stamp] starting 6E collector"
& $python -u $script *>> $log
$exitCode = $LASTEXITCODE
$stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
Add-Content -LiteralPath $log -Value "[$stamp] collector exited code=$exitCode"
exit $exitCode


