@echo off
title SnapStreak Studio Server (Port 8080)
cd /d "%~dp0"

set "PYTHONUNBUFFERED=1"
echo ========================================================
echo  Starting SnapStreak Studio Server on http://localhost:8080
echo ========================================================

start "" "http://localhost:8080"

if exist "..\.venv\Scripts\python.exe" (
    "..\.venv\Scripts\python.exe" run_server.py
) else if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" run_server.py
) else if exist "..\..\snapstreak-server\.venv\Scripts\python.exe" (
    "..\..\snapstreak-server\.venv\Scripts\python.exe" run_server.py
) else (
    python run_server.py
)
pause
