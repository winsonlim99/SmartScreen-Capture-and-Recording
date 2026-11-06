BUILD FIX

The old Build_cxFreeze.bat used generic `py`, which may select the wrong architecture.
Use Build_cxFreeze_x86.bat for C:\Python313-32 or Build_cxFreeze_x64.bat for C:\Python313-64.

x86 NOTES
Python 3.13 32-bit packages may be unavailable for OpenCV or imageio-ffmpeg.
The updated setup allows OpenCV to be absent and can bundle a separately supplied
compatible 32-bit ffmpeg.exe at ffmpeg\ffmpeg.exe. Do not use an x64 FFmpeg binary.
The script checks the Windows PE architecture of FFmpeg and requires it to start.
If you cannot obtain a trusted compatible x86 FFmpeg build, video recording cannot
be guaranteed for x86. Use the x64 edition on 64-bit equipment PCs when possible.

Before retrying, remove only failed local build and incomplete Release test folders.
If release already exists, increase internal release version before rebuilding.
For easier troubleshooting use a short directory such as C:\SmartScreenBuild.
If failure persists, send build_x86.log (or build_x64.log).
