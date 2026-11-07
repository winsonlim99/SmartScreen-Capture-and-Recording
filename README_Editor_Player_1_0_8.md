# Build 1.0.8 — embedded player and visual trim timeline

Open **Edit Video…** after stopping recording.

## Using the editor

- **Add files:** drag one or more local video files from Explorer onto the editor,
  file list or preview, or use **Add videos**. Filenames with spaces, Unicode and
  braces are parsed as native Tcl file lists. Dropping folders is rejected.
- **Play:** select a file and press **Play selection**. Video and audio play inside
  the x64 application; press **Pause** to stop at the current position. Playback
  ends at the selected range boundary. The Volume slider controls preview audio
  only, not exported audio. No external media player is launched.
- **Scrub:** drag the yellow playhead on the timeline bar to inspect a source
  position. Seeking pauses playback and refreshes the frame automatically.
- **Select a range:** drag the green **START** and **END** handles above the bar.
  The blue portion is retained on export. The preview shows the adjusted boundary;
  the numeric range updates immediately. Handles snap to the source frame interval
  and cannot cross. Numeric start/end fields and **Apply range** remain available.
- **Step:** use **◀ Frame** / **Frame ▶** while paused to move by one source-frame
  interval. Times and the selected range are shown beneath the timeline.
- **Trim/join:** retain one range per clip, arrange entries with Move up/down,
  choose output resolution/FPS, and export a new MP4. **Remove last** still defaults
  to five seconds. Originals and existing output files remain protected.
- **Resize:** the editor is now an independent, nonmodal, resizable window with
  native maximize controls and a **Maximize / Restore** button. Preview and timeline
  adapt to its size. Switching applications does not install an input grab or
  pause the main Tk event loop. Recording/screenshots remain blocked while editing.

## Responsiveness and recovery

The prior editor used `grab_set()` and a transient owner, and frame previews were
handled as operations that disabled all editing controls. These were plausible
contributors to the reported focus problem; a Windows hang dump was not supplied,
so the exact original Windows hang is not claimed as reproduced.

The new editor removes the modal grab/transient owner. A dedicated worker owns
all decoder operations. Tk only renders the newest delivered frame; the frame
queue is bounded to one item. Seek requests cancel obsolete FFmpeg previews and
coalesce rapid timeline drags. No decoding, native player shutdown or FFmpeg
waiting occurs in a Tk callback. Playback state is reconciled after an unfocused
period even if the last frame replaces an end-of-selection notification.

Metadata loading/export still run in a cancellable worker. Errors are displayed
without stopping polling. Close cancels pending previews/playback and waits for
workers without blocking window events. No editor processes should remain after
closing the window. Application auto-update remains deferred while editing.

## Build requirements and platform limits

- Recommended: **Windows x64, Python 3.13 with Tcl/Tk 8.6**, using
  `Build_cxFreeze_x64.bat`. `requirements-build.txt` now installs
  `tkinterdnd2==0.4.3` and `ffpyplayer==4.5.3` as well as existing dependencies.
- The x64 Python 3.13 player wheel was verified available. cx_Freeze explicitly
  includes the native Tcl/DLL drag-drop files and FFmpeg/SDL player DLL directories;
  `verify_build.py` checks their presence. The short metadata/output-path fix remains.
- **x86:** the pinned player has no Python 3.13 win32 wheel. The x86 helper retains
  drag-and-drop, timeline, still-frame preview and trim/join export, but embedded
  playback/audio requires x64. Pressing Play explains this limitation. Use the x86
  helper's dependency installation rather than the x64 requirements file.
- The supplied drag-drop extension is compiled for Tcl 8, not Tcl 9. Builds now
  explain this incompatibility rather than shipping a broken drop target. A source
  run on an incompatible Tcl runtime still offers Add videos.
- Windows blocks ordinary Explorer drops into an elevated application. Prefer
  running SmartScreen at the same privilege level as Explorer. Global keyboard
  hook access may have different requirements on restricted equipment PCs.

## Validation

On Linux with Python 3.13/Tk 8.6, the actual GUI test loaded the native tkdnd library,
submitted a multi-file drop containing spaces/braces/Unicode, dragged both trim
handles using Tk mouse events, played/paused embedded audio/video, stepped a frame,
resized, changed focus repeatedly and switched to a separate `xmessage` process.
It also withheld Tk event processing temporarily to verify bounded frame delivery
and recovery when playback reaches the selected end. The existing real GUI
trim/reorder/export test still runs. The drop callback is exercised with native
file-list data; a physical Windows Explorer drag has not been performed.

Decoder tests use the actual ffpyplayer library with an audio dummy device in CI:
playback advances in real time, seek/resume works, selected end stops playback,
latest seek wins, frames stay bounded and worker threads close. Physical speaker
output is not verified by those tests. Media export, metadata, selector, recording,
WGC wrapper and updater tests remain available.

```powershell
python -m unittest -v test_build_metadata test_region_selector test_recording test_window_capture test_video_editing test_video_playback
python -m unittest -v test_video_editor_ui
python test_update.py
```

GUI tests require a display. Linux audio-less CI can use `SDL_AUDIODRIVER=dummy`;
do not set that variable for normal audible playback. Native maximize assertions
run on Windows; Linux tests exercise resizing. Windows frozen-build startup,
Explorer drag, native maximize/restore, physical audio, Alt-Tab and HMI hardware
capture still need a Windows check before equipment deployment.
