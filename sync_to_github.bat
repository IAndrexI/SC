@echo off
title Sync SnapStreak to GitHub
cd /d "%~dp0"

set "GIT_EXE=C:\Users\Andrex\AppData\Local\Programs\Git\cmd\git.exe"

echo ========================================================
echo  Syncing SnapStreak Project to GitHub
echo ========================================================
echo.

if not exist "%GIT_EXE%" (
    echo Git executable not found at %GIT_EXE%
    pause
    exit /b 1
)

set "REPO_URL=%~1"
if "%REPO_URL%"=="" (
    set /p REPO_URL="Enter your GitHub Repository URL (e.g., https://github.com/username/repo.git): "
)

if "%REPO_URL%"=="" (
    echo No repository URL entered. Exiting.
    pause
    exit /b 1
)

"%GIT_EXE%" remote remove origin >nul 2>&1
"%GIT_EXE%" remote add origin "%REPO_URL%"
"%GIT_EXE%" branch -M main
echo.
echo Pushing to GitHub...
"%GIT_EXE%" push -u origin main

if %errorlevel% equ 0 (
    echo.
    echo ========================================================
    echo  Successfully synced all files to GitHub!
    echo ========================================================
) else (
    echo.
    echo Push encountered an error. If prompted for password, use a GitHub Personal Access Token (PAT).
)
pause
