32-BIT WINDOWS BUILD — SmartScreen Capture & Recording V1.0

1. Install Python 3.13 32-bit at C:\Python313-32\python.exe.
2. Run Build_cxFreeze_x86.bat from this project directory.
3. The script checks that Python really is x86, installs build dependencies,
   builds into build\SmartScreen_Capture_V1_0_x86, and creates a separately
   named release under Release\SmartScreen_Capture_V1_0_1_x86.
4. Preserve an independent x86 server Current channel. Set each x86 PC's
   update_source.txt to that x86 Current folder, never the x64 channel.
5. For the existing 64-bit build, continue to use Build_cxFreeze.bat.

WARNING: 32-bit Windows wheels for OpenCV, cx_Freeze or imageio-ffmpeg
may be unavailable for Python 3.13 on your machine. In that case the build
will stop with a dependency error. It is not safe to bundle an x64 ffmpeg.exe
into an application intended for a 32-bit-only Windows system.

The actual x86 cx_Freeze EXE and FFmpeg runtime must be built/tested on Windows.
