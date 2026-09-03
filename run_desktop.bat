@echo off
title Snapchat Streak Bot Desktop
cd /d "%~dp0"

echo ===================================================
echo  Starting Snapchat Streak Bot (Desktop Mode)
echo ===================================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH!
    echo Please install Python 3.10+ from https://www.python.org/
    pause
    exit /b 1
)

echo Checking dependencies...
python -m pip install -r requirements.txt
python -m playwright install chromium

echo.
echo Launching bot...
python run_desktop.py

pause
