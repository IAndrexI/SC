@echo off
title Configure Windows Auto-Login
cd /d "%~dp0"

echo ========================================================
echo  Opening Microsoft Autologon (Administrator)
echo ========================================================
echo.
echo Please click "Yes" on the Windows prompt if asked.
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process '%~dp0Autologon.exe' -ArgumentList '/accepteula' -Verb RunAs"
