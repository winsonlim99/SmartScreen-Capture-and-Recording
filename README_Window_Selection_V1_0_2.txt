SmartScreen Capture & Recording V1.0 — internal release 1.0.2

NEW
1. Custom Region: left-button drag to draw; release left button; right-click confirms.
   Enter still confirms; Esc cancels. A valid selection must be at least 32x32 px.
2. Selected Window: choose "Selected Window" in Area menu; click "Select Window";
   click a visible application/HMI window to choose it. The selected window's
   current desktop bounds are checked on each frame, so the recording follows
   movement/resizing of that window.
3. "Show Window" briefly highlights the selected window bounds.

LIMITATIONS
Selected Window uses visible desktop screen cropping, not a hardware-independent
or occlusion-independent API. Windows on top of the selected application may be
recorded. If the target window closes or minimizes, recording terminates with
an error and finalizes the current MP4 if possible. If the target becomes
partly offscreen or the desktop is locked, frame capture may fail.
Window handles are only valid in the current Windows login session and are
not persisted in config.json. Select the target again after restarting SmartScreen.

PRESERVED
- Screenshot capture and shortcuts
- Full Screen and fixed Custom Region
- FFmpeg/OpenCV fallback, segmented MP4s, optional preview, recording status
- config.json beside EXE and startup-only auto-update
- Separate x86 and x64 cx_Freeze builds (Windows)

BUILD
For 64-bit: Run Build_cxFreeze_x64.bat on the Windows development machine.
For 32-bit: Run Build_cxFreeze_x86.bat with an architecture-compatible FFmpeg.
Build outputs use short local paths under %LOCALAPPDATA%\SmartScreenBuild.

TEST ON EQUIPMENT PC
- Custom Region: left-drag, right-click confirmation; Esc cancellation
- Window selection on first and second monitors (if fitted)
- Move/resize selected window during a short recording
- Close/minimize selected window; verify safe recording finalization
- Check occlusion limitation and playback quality
- Verify update from internal build 1.0.1 to 1.0.2 in a test environment
