@echo off
title Snapchat Streak Bot Desktop
cd /d "%~dp0"

set "PATH=%USERPROFILE%\.local\bin;%PATH%"

echo ===================================================
echo  Starting Snapchat Streak Bot (Desktop Mode)
echo ===================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo Setting up Python 3.11 environment with uv...
    uv venv .venv --python 3.11
    uv pip install -r requirements.txt
    .venv\Scripts\python -m playwright install chromium
)

echo Launching bot...
".venv\Scripts\python.exe" run_desktop.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Bot exited with error code %ERRORLEVEL%.
)
echo.
pause
