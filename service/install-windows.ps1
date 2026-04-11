# Install Claude Dispatcher as a Windows service using NSSM
# Run as Administrator
#
# First install NSSM: winget install nssm  (or choco install nssm)

$ServiceName = "ClaudeDispatcher"
$ProjectDir = Split-Path -Parent $PSScriptRoot
$PythonExe = Join-Path $ProjectDir "venv\Scripts\python.exe"
$BotScript = Join-Path $ProjectDir "bot.py"

# Check NSSM
if (-not (Get-Command nssm -ErrorAction SilentlyContinue)) {
    Write-Error "NSSM not found. Install: winget install nssm"
    exit 1
}

# Install service
nssm install $ServiceName $PythonExe $BotScript
nssm set $ServiceName AppDirectory $ProjectDir
nssm set $ServiceName DisplayName "Claude Dispatcher Bot"
nssm set $ServiceName Description "Telegram bot for remote Claude Code session management"
nssm set $ServiceName Start SERVICE_AUTO_START
nssm set $ServiceName AppStdout (Join-Path $ProjectDir "logs\service-stdout.log")
nssm set $ServiceName AppStderr (Join-Path $ProjectDir "logs\service-stderr.log")
nssm set $ServiceName AppRotateFiles 1
nssm set $ServiceName AppRotateBytes 5242880  # 5MB

# Start
nssm start $ServiceName
Write-Host "Service '$ServiceName' installed and started."
Write-Host "  Stop:    nssm stop $ServiceName"
Write-Host "  Remove:  nssm remove $ServiceName confirm"
Write-Host "  Status:  nssm status $ServiceName"
