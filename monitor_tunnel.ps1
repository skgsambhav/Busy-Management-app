# ================================================
# BusyApp Tunnel Monitor - Auto Recovery Script
# Runs every 5 minutes via Windows Task Scheduler
# ================================================

$logFile = "C:\Users\GOPAL MARKETING\Desktop\BUSY\receipt_app\tunnel_monitor.log"
$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

function Write-Log($msg) {
    $line = "[$timestamp] $msg"
    Add-Content -Path $logFile -Value $line
    # Keep log under 500 lines
    $lines = Get-Content $logFile -ErrorAction SilentlyContinue
    if ($lines -and $lines.Count -gt 500) {
        $lines[-400..-1] | Set-Content $logFile
    }
}

# Test if busyapp is responding locally
$appOk = $false
try {
    $r = Invoke-WebRequest -Uri "http://localhost:5000" -TimeoutSec 5 -UseBasicParsing -ErrorAction Stop
    $appOk = ($r.StatusCode -lt 500)
} catch {
    $appOk = $false
}

# Check Cloudflared service
$cfService = Get-Service Cloudflared -ErrorAction SilentlyContinue
$cfRunning = ($cfService -and $cfService.Status -eq 'Running')

# Check busyapp service
$busyService = Get-Service busyapp -ErrorAction SilentlyContinue
$busyRunning = ($busyService -and $busyService.Status -eq 'Running')

Write-Log "CHECK | App:$appOk | Cloudflared:$cfRunning | BusyApp:$busyRunning"

# Restart busyapp if not running
if (-not $busyRunning) {
    Write-Log "ACTION: busyapp service down - restarting..."
    try {
        Start-Service busyapp -ErrorAction Stop
        Write-Log "OK: busyapp restarted"
    } catch {
        Write-Log "ERROR: Could not restart busyapp - $_"
    }
    Start-Sleep -Seconds 5
}

# Restart Cloudflared if not running
if (-not $cfRunning) {
    Write-Log "ACTION: Cloudflared down - restarting..."
    try {
        Start-Service Cloudflared -ErrorAction Stop
        Write-Log "OK: Cloudflared restarted"
    } catch {
        Write-Log "ERROR: Could not restart Cloudflared - $_"
    }
}

Write-Log "DONE"
