@echo off
title SnapStreak - Extension Permanent Installer
cd /d "%~dp0"

echo ========================================================
echo  SnapStreak Extension Permanent Installation Guide
echo ========================================================
echo.
echo Extension folder is located at:
echo  %~dp0extension
echo.
echo 1. Opening Brave Extensions page (brave://extensions)...
echo 2. Toggle "Developer mode" ON (top right).
echo 3. Click "Load unpacked" (top left).
echo 4. Select the folder: %~dp0extension
echo.

set "BRAVE_EXE=%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe"
if exist "%BRAVE_EXE%" (
    start "" "%BRAVE_EXE%" "brave://extensions"
) else (
    start "" "chrome://extensions"
)

pause
