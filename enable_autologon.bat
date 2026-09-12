@echo off
title Enable Windows Auto-Login
cd /d "%~dp0"

:: Check for Administrator privileges
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Requesting Administrator privileges...
    powershell -Command "Start-Process cmd.exe -ArgumentList '/c', '\"\"\"%~f0\"\"\"' -Verb RunAs"
    exit /b
)

echo ===================================================
echo  Configuring Windows Auto-Login (AutoAdminLogon)
echo ===================================================
echo.

echo [1/2] Updating Windows Hello settings...
reg add "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\PasswordLess\Device" /v DevicePasswordLessBuildVersion /t REG_DWORD /d 0 /f

echo [2/2] Launching Microsoft Sysinternals Autologon...
echo.
echo Enter your Windows account password in the Autologon dialog and click "Enable".
echo.
start "" "%~dp0Autologon.exe" /accepteula Andrex %USERDOMAIN%

echo.
echo Configuration finished!
timeout /t 5
