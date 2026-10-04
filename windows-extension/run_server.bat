@echo off
title Snapchat Streak Bot - Mini Server
cd /d "%~dp0"

set "PATH=%USERPROFILE%\.local\bin;%PATH%"
set "PYTHONUNBUFFERED=1"

echo ===================================================
echo  Starting Snapchat Streak Bot - Local Server
echo ===================================================
echo.
echo Dashboard URL: http://localhost:8080
echo.

start "" "http://localhost:8080"

".venv\Scripts\python.exe" run_server.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Server stopped with exit code %ERRORLEVEL%.
    pause
)
