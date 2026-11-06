@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "PY64=C:\Python313-64\python.exe"
set "SMARTSCREEN_BUILD_ARCH=x64"
set "LOG=%~dp0build_x64.log"
if not exist "%PY64%" (echo Missing %PY64%& goto :fail)
"%PY64%" -c "import struct,sys; print(sys.executable,struct.calcsize('P')*8);sys.exit(0 if struct.calcsize('P')==8 else 1)"
if errorlevel 1 goto :fail
"%PY64%" -m pip install -r requirements-build.txt
if errorlevel 1 goto :fail
"%PY64%" -m pip install windows-capture==2.0.1
if errorlevel 1 goto :fail
"%PY64%" prepare_build.py
if errorlevel 1 goto :fail
"%PY64%" setup.py build > "%LOG%" 2>&1
if errorlevel 1 (type "%LOG%"& goto :fail)
"%PY64%" verify_build.py >> "%LOG%" 2>&1
if errorlevel 1 (
 echo Build DLL verification failed:
 type "%LOG%"
 goto :fail
)
"%PY64%" make_release.py >> "%LOG%" 2>&1
if errorlevel 1 (type "%LOG%"& goto :fail)
echo SUCCESS: build completed.
"%PY64%" -c "from build_paths import BUILD,RELEASE_ROOT;print('EXE output:',BUILD);print('Release folder:',RELEASE_ROOT)"
pause
exit /b 0
:fail
echo Build failed. Send build_x64.log.
pause
exit /b 1
