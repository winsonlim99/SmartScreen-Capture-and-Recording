SmartScreen V1.0 (internal 1.0.5) - independent Selected Window recording

Windows Graphics Capture (WGC) via windows-capture==2.0.1 is bundled only in the x64 build.
Selected Window captures the chosen HWND, not desktop coordinates. Switching to another
application does not replace the selected HMI frames. The HMI must remain open and not
minimized. Certain protected/specialized/legacy HMI rendering may not be capturable.

x64: Run Build_cxFreeze_x64.bat on a supported Windows machine. It installs the WGC package.
x86: Existing x86 build continues to support Full Screen and Custom Region. Selected
Window will show an explicit unsupported error; it will NOT silently capture another window.

Other behavior retained: FFmpeg recording/segmentation, local config, screenshots, auto update.
Do not publish 1.0.5 to production before real HMI testing. Check CPU/FPS and playback.

Build 1.0.5 updates smart_update.APP_VERSION and setup.APP_VERSION consistently.
