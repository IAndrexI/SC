@echo off
title SnapStreak - Snapchat Web with Live SJSU Meteorology Webcam
cd /d "%~dp0"

echo ========================================================
echo  Launching Snapchat Web with SJSU Meteorology Webcam
echo ========================================================
echo.

set "EXT_DIR=%~dp0extension"
set "DATA_DIR=%~dp0desktop_data"
set "BRAVE_EXE=%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe"

REM Refresh latest live SJSU meteorology frame into webcam.y4m
if exist ".venv\Scripts\python.exe" (
    echo [1/2] Refreshing live SJSU Meteorology camera feed...
    ".venv\Scripts\python.exe" -c "import sys, pathlib; sys.path.insert(0, 'app'); import automation; data = automation.fetch_webcam_image(force_refresh=True); automation.generate_y4m_from_image(data, out_path=pathlib.Path(r'%DATA_DIR%\webcam.y4m'))"
)

set "CAM_FLAGS=--use-fake-ui-for-media-stream --use-fake-device-for-media-stream --use-file-for-fake-video-capture=%DATA_DIR%\webcam.y4m"
set "BROWSER_FLAGS=--disable-session-crashed-bubble --no-first-run --no-default-browser-check"

echo [2/2] Launching browser with live SJSU webcam and SnapStreak HUD...

if exist "%BRAVE_EXE%" (
    start "" /high "%BRAVE_EXE%" --load-extension="%EXT_DIR%" %CAM_FLAGS% %BROWSER_FLAGS% "https://web.snapchat.com/"
) else (
    start "" /high chrome.exe --load-extension="%EXT_DIR%" %CAM_FLAGS% %BROWSER_FLAGS% "https://web.snapchat.com/"
)

echo.
echo ========================================================
echo  Snapchat is now running with the live SJSU Meteorology
echo  feed set as your system webcam!
echo ========================================================
echo.
