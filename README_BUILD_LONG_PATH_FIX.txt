SmartScreen Capture & Recording V1.0 - cx_Freeze long-path fix

Root cause from build_x64.log: the failing destination path is 261 characters.
cx_Freeze was copying NumPy's OpenBLAS DLL into the deeply nested build folder
and failed during setup.py build, before post-build DLL verification could run.

FIX: build_paths.py places the output under the current user's LOCALAPPDATA:
  %LOCALAPPDATA%\SmartScreenBuild\build\SmartScreen_Capture_V1_0\  (x64)
  %LOCALAPPDATA%\SmartScreenBuild\build\SmartScreen_Capture_V1_0_x86\ (x86)
  %LOCALAPPDATA%\SmartScreenBuild\Release\... (versioned release)

Build normally with Build_cxFreeze_x64.bat or Build_cxFreeze_x86.bat.
This package preserves the existing Python code, encoder, logo and updater.
The publisher script in each generated Release folder can still publish to
server Current. Do not mix x86 and x64 Current folders.

Optional custom destination (set BEFORE running .bat):
  set SMARTSCREEN_OUTPUT_ROOT=C:\SmartScreenBuild

IMPORTANT: The batch script will install required Python packages if necessary.
The build must be tested on Windows. Do not copy missing NumPy DLLs from
another architecture or from untrusted download sites.
