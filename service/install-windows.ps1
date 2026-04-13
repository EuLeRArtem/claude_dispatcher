# Install Claude Dispatcher as a Windows Scheduled Task
# Run as Administrator
#
# The task runs in the current user's session (not Session 0),
# so GUI apps (VS Code, Cursor) can open windows normally.

$TaskName = "ClaudeDispatcher"
$ProjectDir = Split-Path -Parent $PSScriptRoot
$PythonExe = Join-Path $ProjectDir "venv\Scripts\pythonw.exe"
$BotScript = Join-Path $ProjectDir "bot.py"

if (-not (Test-Path $PythonExe)) {
    Write-Error "Python venv not found at $PythonExe. Run: python -m venv venv && pip install -r requirements.txt"
    exit 1
}

# Remove existing task if any
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

# Action: run bot.py via venv python
$Action = New-ScheduledTaskAction `
    -Execute $PythonExe `
    -Argument $BotScript `
    -WorkingDirectory $ProjectDir

# Trigger: at user logon
$Trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME

# Settings: restart on failure, don't stop on idle, run indefinitely
$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1)

# Register task — runs as current user, interactive session (NOT "Run whether user is logged on or not")
Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Description "Telegram bot for remote Claude Code session management" `
    -RunLevel Limited

Write-Host ""
Write-Host "Task '$TaskName' registered successfully."
Write-Host "  It will start automatically at logon."
Write-Host ""
Write-Host "Manual control:"
Write-Host "  Start:   Start-ScheduledTask -TaskName $TaskName"
Write-Host "  Stop:    Stop-ScheduledTask -TaskName $TaskName"
Write-Host "  Remove:  Unregister-ScheduledTask -TaskName $TaskName"
Write-Host "  Status:  Get-ScheduledTask -TaskName $TaskName | Select State"
Write-Host ""
Write-Host "Starting now..."
Start-ScheduledTask -TaskName $TaskName
Write-Host "Done. Check status: Get-ScheduledTask -TaskName $TaskName | Select State"
