@echo off
title YoursBuddy AI - Desktop Chrome Bridge Agent
cls
echo ==============================================================================
echo    YoursBuddy AI - Desktop Chrome Bridge Agent Launcher
echo ==============================================================================
echo.
echo  This tool securely connects your local desktop Google Chrome browser to
echo  the cloud AI backend on Render (https://javis-backend-3pfy.onrender.com).
echo.
echo  * Outbound connection only (WebSocket / HTTP)
echo  * Port 9222 remains completely safe on localhost (NEVER exposed to internet)
echo  * Multi-user workspace isolation enabled
echo ==============================================================================
echo.

:: 1. Check Python
where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python was not found in your system PATH.
    echo Please install Python 3.10+ from python.org and add it to PATH.
    pause
    exit /b 1
)

:: 2. Find Google Chrome executable
set "CHROME_EXE="
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" (
    set "CHROME_EXE=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
) else if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" (
    set "CHROME_EXE=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
) else if exist "%LocalAppData%\Google\Chrome\Application\chrome.exe" (
    set "CHROME_EXE=%LocalAppData%\Google\Chrome\Application\chrome.exe"
)

:: 3. Launch Chrome on port 9222 if not already listening
echo [1/3] Checking desktop Chrome status on port 9222...
powershell -Command "try { $r = Invoke-WebRequest -Uri 'http://127.0.0.1:9222/json/version' -TimeoutSec 1 -UseBasicParsing; exit 0 } catch { exit 1 }" >nul 2>nul
if %ERRORLEVEL% equ 0 (
    echo [OK] Desktop Chrome is already running with remote debugging on port 9222.
) else (
    if defined CHROME_EXE (
        echo [OK] Launching desktop Chrome with remote debugging on localhost:9222...
        start "" "%CHROME_EXE%" --remote-debugging-port=9222 --user-data-dir="%LOCALAPPDATA%\Google\Chrome\AutomationData" --no-first-run --no-default-browser-check --mute-audio "https://www.linkedin.com"
        timeout /t 2 /nobreak >nul
    ) else (
        echo [NOTICE] Chrome executable not found in default paths.
        echo Please launch Chrome manually with:
        echo chrome.exe --remote-debugging-port=9222 --user-data-dir="%%LOCALAPPDATA%%\Google\Chrome\AutomationData"
    )
)

:: 4. Ask for Workspace ID if desired (default: default)
set "AGENCY_ID=default"
if not "%~1"=="" (
    set "AGENCY_ID=%~1"
) else (
    set /p "USER_INPUT_ID=Enter Workspace ID (press ENTER for default): "
    if not "%USER_INPUT_ID%"=="" set "AGENCY_ID=%USER_INPUT_ID%"
)

echo.
echo [2/3] Workspace selected: %AGENCY_ID%
echo [3/3] Starting bridge agent connection to Render cloud backend...
echo ==============================================================================
echo.

python scripts\local_agent.py --backend https://javis-backend-3pfy.onrender.com --agency-id "%AGENCY_ID%"

if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] Bridge agent exited with error code %ERRORLEVEL%.
    pause
)
