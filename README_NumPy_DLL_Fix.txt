SmartScreen Capture & Recording V1.0 — NumPy DLL and architecture build correction

1. Extract to a short path such as C:\SmartScreenBuild\.
2. Use Build_cxFreeze_x86.bat for C:\Python313-32, or Build_cxFreeze_x64.bat for C:\Python313-64.
3. Build scripts now clean ONLY the chosen architecture's build folder, avoiding mixing files.
4. verify_build.py verifies and copies any missing numpy.libs DLLs from the same Python interpreter. Never copy NumPy DLLs across x86 and x64.
5. If the build still fails, inspect build_x86.log or build_x64.log. Find the FIRST Traceback, not merely the last line.
6. Release packaging refuses to overwrite an existing versioned Release directory. Increment the internal APP_VERSION when publishing a new version, or remove only an incomplete test release.
7. Run SmartScreen_Capture.exe on a test Windows equipment PC before publishing Current.

If the missing DLL error occurs DURING cx_Freeze copying (rather than make_release), please share the first failing Traceback; NumPy/cx_Freeze wheel compatibility may require pinning versions.
