@echo off
title SnapStreak Desktop Runner
cd /d "%~dp0"

set "PYTHONUNBUFFERED=1"
echo ========================================================
echo  Launching SnapStreak Desktop Runner
echo ========================================================

if exist "..\.venv\Scripts\python.exe" (
    "..\.venv\Scripts\python.exe" run_desktop.py %*
) else if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" run_desktop.py %*
) else if exist "..\..\snapstreak-server\.venv\Scripts\python.exe" (
    "..\..\snapstreak-server\.venv\Scripts\python.exe" run_desktop.py %*
) else (
    python run_desktop.py %*
)
pause
