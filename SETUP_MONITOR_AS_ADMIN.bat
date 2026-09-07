@echo off
echo =============================================
echo  BusyApp Auto-Monitor Setup (Admin Required)
echo =============================================

:: Register Scheduled Task as SYSTEM (needs admin)
powershell.exe -NonInteractive -ExecutionPolicy Bypass -Command ^
"$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument '-NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File ""C:\Users\GOPAL MARKETING\Desktop\BUSY\receipt_app\monitor_tunnel.ps1""'; ^
$trigger = New-ScheduledTaskTrigger -RepetitionInterval (New-TimeSpan -Minutes 5) -Once -At (Get-Date); ^
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 2) -StartWhenAvailable -RunOnlyIfNetworkAvailable; ^
$principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest; ^
Register-ScheduledTask -TaskName 'BusyApp-TunnelMonitor' -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description 'Auto-monitors busyapp + Cloudflared every 5 min' -Force; ^
Write-Host 'SUCCESS: Task registered!' -ForegroundColor Green"

if %errorlevel% == 0 (
    echo.
    echo SUCCESS! Auto-monitor registered.
    echo BusyApp aur Cloudflared ab har 5 minute mein check honge.
    echo Log file: C:\Users\GOPAL MARKETING\Desktop\BUSY\receipt_app\tunnel_monitor.log
) else (
    echo.
    echo ERROR: Admin rights se run karo!
    echo Is file pe Right-click karke "Run as Administrator" select karo.
)

pause
