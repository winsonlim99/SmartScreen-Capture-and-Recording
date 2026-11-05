@echo off
setlocal
cd /d "%~dp0"
py -m pip install -r requirements-build.txt
if errorlevel 1 goto :fail
py setup.py build
if errorlevel 1 goto :fail
echo.
py -3 make_release.py
if errorlevel 1 goto :fail
echo Build complete: build\SmartScreen_Capture_V1_0
echo Copy the entire output directory to equipment PCs.
pause
exit /b 0
:fail
echo Build failed. Review the errors above.
pause
exit /b 1
