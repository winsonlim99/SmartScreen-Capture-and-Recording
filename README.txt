SmartScreen Capture & Recording V1.0
====================================

CONTENTS
SmartScreen_Capture_V1_0.py  - Python application
setup.py                     - cx_Freeze build settings (bundles FFmpeg from imageio-ffmpeg)
Build_cxFreeze.bat           - Windows build helper
requirements-build.txt      - required Python packages
assets/                     - application logo

BUILD (WINDOWS)
1. Install the correct Windows Python architecture (32-bit or 64-bit) for your PC.
2. Extract this package to a writable folder.
3. Double-click Build_cxFreeze.bat; it installs requirements and runs setup.py build.
4. Copy the ENTIRE build/SmartScreen_Capture_V1_0 folder to compatible equipment PCs.
5. Click Check Recorder before actual use. Test 720p / 10 FPS first.

NEW RECORDING CONTROLS
- The dedicated Hide to Taskbar button was removed. Normal Windows minimize is available from the title bar.
- Red REC label, elapsed timer, active filename, current segment number and size.
- Windows taskbar icon displays a red indicator while recording; taskbar flashes briefly
  after the first captured video frame. No popup obscures equipment HMI.
- Recording continues while the application is minimized.
- Video files roll to the next numbered MP4 when they approach 850 MB (decimal).
  The conservative rollover threshold leaves headroom for MP4 finalization and buffering.
- A completed file is checked against the 1 GB limit. Since encoder buffering varies,
  hardware validation is required; exact 1 GB enforcement is not mathematically guaranteed.
- Recording stops and finalizes when available disk space falls below 2 GB.
- When Save As is Operation, parts are Operation01.mp4, Operation02.mp4, etc.
- When Save As is empty, parts are Recording_YYYYMMDD_HHMMSS_01.mp4, _02.mp4, etc.
- Closing the program during recording finalizes video before exit.
- Existing screenshot shortcuts, delay, optional previews, and screenshot naming remain.

LIMITATIONS
- Switching encoders between MP4 segments may cause a small recording gap.
- Windows notifications are implemented as a brief TASKBAR flash and persistent red
  taskbar icon/title, not a foreground popup that could be recorded in the video.
- Requires a logged-in interactive Windows desktop. Screen capture may not work for
  protected HMI windows or secure desktop sessions.
- Actual cx_Freeze EXE build and Windows equipment tests must be run on Windows.
- For machines close to the disk threshold, choose another drive with >= 2 GB free.

CONFIG FILE LOCATION
- config.json is saved strictly alongside SmartScreen_Capture.exe.
- During development with Python, config.json is saved alongside the .py file.
- Existing AppData configs are NOT automatically migrated; transfer required settings
  into the EXE folder's config.json if previously stored elsewhere.
- Install/copy to a user-writable directory, e.g. C:\APP\SmartScreen_Capture_V1_0.
- Program Files and other protected directories may block configuration saving.
- The taskbar icon shows a red REC indicator and briefly flashes on recording start;
  the running timer/filename are displayed inside the window when restored.

WINDOW MINIMIZATION
- Use the normal Windows title-bar minimize control when needed.
- The "Minimize before capture / recording" checkbox remains available.
- Recording continues while the application is minimized.
- Automatic minimize/restore behavior for capture and recording remains unchanged.
- On failure, inspect %APPDATA%\screenshot_app\capture_v10.log.
