@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "PY32=C:\Python313-32\python.exe"
set "SMARTSCREEN_BUILD_ARCH=x86"
set "LOG=%~dp0build_x86.log"
if not exist "%PY32%" (
 echo Missing %PY32%
 goto :fail
)
"%PY32%" -c "import struct,sys; print(sys.executable,struct.calcsize('P')*8);sys.exit(0 if struct.calcsize('P')==4 else 1)"
if errorlevel 1 goto :fail
if not exist "ffmpeg\ffmpeg.exe" (
 echo NOTE: No local ffmpeg\ffmpeg.exe. The build will look for imageio-ffmpeg.
 echo For x86, a compatible 32-bit executable may need to be provided manually.
)
"%PY32%" -m pip install --upgrade pip
if errorlevel 1 goto :fail
"%PY32%" -m pip install cx_Freeze pillow keyboard mss numpy imageio tkinterdnd2==0.4.3
if errorlevel 1 goto :fail
REM Optional dependencies must not stop an x86 build when wheels do not exist.
"%PY32%" -m pip install imageio-ffmpeg
"%PY32%" -m pip install opencv-python
"%PY32%" prepare_build.py
if errorlevel 1 goto :fail
"%PY32%" setup.py build > "%LOG%" 2>&1
if errorlevel 1 (
 echo Build failed - see build_x86.log:
 type "%LOG%"
 goto :fail
)
"%PY32%" verify_build.py >> "%LOG%" 2>&1
if errorlevel 1 (
 echo Build DLL verification failed:
 type "%LOG%"
 goto :fail
)
"%PY32%" make_release.py >> "%LOG%" 2>&1
if errorlevel 1 (
 echo Release packaging failed - see build_x86.log:
 type "%LOG%"
 goto :fail
)
echo SUCCESS: build completed.
"%PY32%" -c "from build_paths import BUILD,RELEASE_ROOT;print('EXE output:',BUILD);print('Release folder:',RELEASE_ROOT)"
pause
exit /b 0
:fail
echo 32-bit build failed. If needed, send build_x86.log for diagnosis.
pause
exit /b 1
