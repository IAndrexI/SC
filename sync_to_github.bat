@echo off
title Sync SnapStreak to GitHub (iandrexi/sc)
cd /d "%~dp0"

set "GIT_EXE=C:\Users\Andrex\AppData\Local\Programs\Git\cmd\git.exe"
set "GH_EXE=C:\Users\Andrex\AppData\Local\Programs\Git\cmd\gh.exe"
set "REPO_URL=https://github.com/iandrexi/sc.git"

echo ========================================================
echo  Syncing SnapStreak Project to https://github.com/iandrexi/sc
echo ========================================================
echo.

if not exist "%GIT_EXE%" (
    echo Git executable not found at %GIT_EXE%
    pause
    exit /b 1
)

:: Check GitHub login status
"%GH_EXE%" auth status >nul 2>&1
if %errorlevel% neq 0 (
    echo [1/2] GitHub authorization needed...
    echo.
    echo Opening your browser to authenticate with GitHub...
    echo (If a one-time code appears, copy and paste it into GitHub).
    echo.
    "%GH_EXE%" auth login --web --clipboard -h github.com -p https -s repo
) else (
    echo [1/2] Already logged in to GitHub via GitHub CLI.
)

echo.
echo [2/2] Pushing all project files to origin main...
"%GIT_EXE%" remote remove origin >nul 2>&1
"%GIT_EXE%" remote add origin "%REPO_URL%"
"%GIT_EXE%" branch -M main
"%GIT_EXE%" push -u origin main

if %errorlevel% equ 0 (
    echo.
    echo ========================================================
    echo  SUCCESS: All files synced to https://github.com/iandrexi/sc!
    echo ========================================================
) else (
    echo.
    echo Push encountered an issue. If you use a Personal Access Token (PAT),
    echo you can also paste it when prompted by Git.
)

echo.
pause
