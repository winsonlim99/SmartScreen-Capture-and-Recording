@echo off
setlocal
cd /d "%~dp0"
py -3 publish_release.py
if errorlevel 1 (
  echo Publication FAILED - Current was not updated successfully.
  pause
  exit /b 1
)
echo Verify server Current and Current_Old before removing old release.
pause
