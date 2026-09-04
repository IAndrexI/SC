@echo off
title Snapchat Streak Bot Desktop
cd /d "%~dp0"

echo ===================================================
echo  Starting Snapchat Streak Bot (Desktop Mode)
echo ===================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo Setting up Python 3.11 environment with uv...
    uv venv .venv --python 3.11
    .venv\Scripts\python -m pip install -r requirements.txt
    .venv\Scripts\python -m playwright install chromium
)

echo Launching bot...
.venv\Scripts\python run_desktop.py

pause
