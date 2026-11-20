# YoursBuddy AI - Desktop Chrome Bridge Agent PowerShell Launcher
Param(
    [string]$Backend = "https://javis-backend-3pfy.onrender.com",
    [string]$AgencyId = "default"
)

Write-Host "==============================================================================" -ForegroundColor Cyan
Write-Host "   YoursBuddy AI - Desktop Chrome Bridge Agent (PowerShell)" -ForegroundColor White
Write-Host "==============================================================================" -ForegroundColor Cyan
Write-Host "  Backend:    $Backend"
Write-Host "  Workspace:  $AgencyId"
Write-Host "=============================================================================="

# 1. Test Chrome CDP
$cdpRunning = $false
try {
    $res = Invoke-WebRequest -Uri "http://127.0.0.1:9222/json/version" -TimeoutSec 1 -UseBasicParsing -ErrorAction Stop
    if ($res.StatusCode -eq 200) { $cdpRunning = $true }
} catch {
    $cdpRunning = $false
}

if (-not $cdpRunning) {
    $chromePaths = @(
        "${env:ProgramFiles}\Google\Chrome\Application\chrome.exe",
        "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
        "${env:LocalAppData}\Google\Chrome\Application\chrome.exe"
    )
    $found = $null
    foreach ($p in $chromePaths) {
        if (Test-Path $p) { $found = $p; break }
    }
    if ($found) {
        Write-Host "[1/2] Starting Chrome in standby with remote debugging on port 9222..." -ForegroundColor Yellow
        $userData = "${env:LocalAppData}\Google\Chrome\AutomationData"
        Start-Process $found -ArgumentList "--remote-debugging-port=9222", "--user-data-dir=$userData", "--no-first-run", "--no-default-browser-check", "--mute-audio", "about:blank"
        Start-Sleep -Seconds 2
    }
}

Write-Host "[2/2] Launching Python bridge agent..." -ForegroundColor Green
python scripts/local_agent.py --backend $Backend --agency-id $AgencyId
