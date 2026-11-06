SmartScreen Capture & Recording V1.0 — internal build 1.0.3

WINDOW SELECTION IMPROVEMENTS
- After Select Window, a frozen desktop snapshot appears.
- Moving the mouse shows a green outline for the external top-level window under the cursor.
- The window title and dimensions appear near the upper-left corner.
- Left-click selects the window; Esc cancels.
- SmartScreen's overlay and internal Tk windows are ignored by process ID.
- Selected-window bounds are checked against the selected monitor before recording.
- Show Window now draws a temporary green border without covering the HMI.

IMPORTANT LIMITATIONS
- This is visible desktop cropping, not occlusion-independent capture.
- The selection view uses a screenshot taken when selection began; it is not live HMI video.
- Windows with no title may not be selectable.
- A window partly off the selected monitor must be moved fully within it,
  or change monitor selection to All Monitors before selecting.
- If another application covers the HMI while recording, the obstruction can appear.
- When the HMI is minimized or closes, recording will stop and finalize safely.

BUILD
Use Build_cxFreeze_x64.bat or Build_cxFreeze_x86.bat with suitable FFmpeg.
Use new 1.0.3 manifest/release to publish via the Current/Release updater.

VALIDATION
Syntax and static checks performed on Linux. Mouse highlighting, HWND
selection, MP4 recording, and Windows build require physical Windows tests.
