SMARTSCREEN CAPTURE & RECORDING V1.0 - CURRENT-CHANNEL AUTO UPDATE
=============================================================

PURPOSE
- Same operational release flow as DTMS and TNR DataSafe: Release -> Current.
- Equipment application checks for a higher version ONCE when started.
- Checks, downloads, and SHA-256 validation occur in a background thread.
- Does NOT interrupt active screenshots/video recording.
- A separate Windows PowerShell updater waits for SmartScreen.exe to exit,
  installs files, verifies them, restarts, and rolls back on failures.
- If server is offline/unavailable, run the currently installed version.
- Never overwrite config.json, update_source.txt, logs, or saved recordings.

SERVER FOLDER LAYOUT (configure YOUR approved network location)
<server-root>\SmartScreen_Capture\
    Current\                       [published, verified runtime files]
        version.json
        SmartScreen_Capture.exe
        updater\Apply_Update.ps1
        ... cx_Freeze libraries, assets, FFmpeg ...
    Current_Old\                   [retained previous Current after publishing]
    Release\
        SmartScreen_Capture_V1_0_0\
            version.json
            Publish_Release_To_Current.bat
            publish_release.py
            SmartScreen_Capture.exe
            ...

FIRST BUILD (Windows build PC, installed Python + cx_Freeze)
1. Extract complete ZIP on Windows development PC.
2. Run Build_cxFreeze.bat, which runs:
       py -m pip install -r requirements-build.txt
       py setup.py build
       py -3 make_release.py
3. A build\SmartScreen_Capture_V1_0\ folder and a Release\SmartScreen_Capture_V1_0_0\
   folder are created. The latter has generated version.json and publisher.
4. The build must use suitable Windows architecture/OS/FFmpeg for target PCs.

ADMIN PUBLISH WORKFLOW
1. Copy the complete generated Release\SmartScreen_Capture_V1_0_0 directory
   into your approved network SERVER\SmartScreen_Capture\Release directory.
2. From inside that Release version folder, run Publish_Release_To_Current.bat.
3. The publisher verifies every file, builds Current_New, then switches it
   to Current. If Current previously existed, it is retained as Current_Old.
4. When Current_Old exists, REVIEW it before the next publication and archive
   or remove it manually. This prevents overwriting your rollback copy.
5. Restrict write access to Release and Current to authorized admins.
   SHA-256 detects corrupt changes; it does not authenticate the publisher.

EQUIPMENT-PC DEPLOYMENT
1. Copy ALL contents of build\SmartScreen_Capture_V1_0\ to a writable folder
   such as C:\APP\SmartScreen_Capture_V1_0\.
2. Copy update_source.txt.example to update_source.txt NEXT TO EXE.
3. Replace example server path with the ACTUAL approved Current UNC path:
       \\YOUR-SERVER\YOUR-SHARE\SmartScreen_Capture\Current
   The example is a placeholder, not a real SiliconBox server path.
4. Make sure the logged-in user has READ access to Current and WRITE access
   to the local application directory. No Python on equipment PCs.
5. Leave config.json in the same directory as SmartScreen_Capture.exe.
6. Launch SmartScreen_Capture.exe. No update occurs if Current is same/older.

NEXT RELEASE (example 1.0.1)
1. Edit / develop the source code in the project folder.
2. Run:  py Set_Release_Version.py 1.0.1
3. IMPORTANT: delete/move any previous Release\SmartScreen_Capture_V1_0_1
   before building; make_release refuses to overwrite an existing release.
4. Run Build_cxFreeze.bat.
5. Publish NEW version folder from its Publish_Release_To_Current.bat.
6. Restart one TEST equipment PC. The verified higher version is applied.
7. If video recording is already active when update finishes staging, the
   update is DEFERRED until next application startup. No video is interrupted.

ON-DEVICE UPDATE OPERATION
- Exits ONLY after external updater acknowledges it is running.
- External updater waits for original process to exit (max 60 seconds).
- Existing files are backed up under .update_backup; new files are tracked.
- Verifies installed file hashes, launches new EXE and waits up to 35 seconds
  for a GUI-started acknowledgement.
- On failure, restores old files and relaunches prior application.
- On success, deletes backup and temporary staged release files.
- update.log stays beside the EXE for troubleshooting.

LIMITATIONS / IMPORTANT TESTS
- A GUI-started acknowledgement detects immediate startup failure, but does
  not prove video encoding, machine HMI capture, or long-term stability.
- The update replaces app binaries only; no removal of stale old library files.
- PowerShell execution can be blocked by corporate Group Policy; test with IT.
- Manual copy of first package is required before startup auto-update works.
- Install must be tested on Windows; Linux tests cannot validate locked DLLs,
  native taskbar behavior, or PowerShell process startup.
- Applications/other processes locking DLLs may prevent an update and require
  an IT-supported restart.
