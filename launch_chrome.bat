@echo off
title YoursBuddy AI Chrome Launcher
echo =======================================================
echo   YoursBuddy AI - Desktop Chrome Controller
echo =======================================================
echo.
echo Starting Google Chrome for YoursBuddy AI...
echo (LinkedIn and YouTube will open in separate tabs)
echo.

start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="%LOCALAPPDATA%\Google\Chrome\AutomationData" --no-first-run --no-default-browser-check --start-maximized --mute-audio

echo Chrome is running with automation support on port 9222!
echo You can keep this browser window open on your screen.
timeout /t 3 >nul
