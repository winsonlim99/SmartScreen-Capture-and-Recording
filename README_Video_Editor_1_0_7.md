# Build 1.0.7: Edit Video — Trim and Join

Open **Edit Video…** beside Check Recorder and Save Config after stopping recording.
No time is automatically removed from recordings.

1. **Add videos** loads local files in join order. Select an entry to see its range.
2. Drag the preview slider and press **Preview frame at slider** to inspect a
   position. **Play original in player** opens the original in your default player;
   the embedded preview is a seekable still frame, not a real-time player.
3. Enter **Keep from** and **to** in seconds (decimals accepted), then **Apply range**.
   **Remove last** defaults to 5 seconds and accepts another positive duration.
   It sets the end relative to the original duration; repeated clicks do not
   repeatedly subtract time. A removal that would leave an empty clip is rejected.
4. **Move up/down** sets join order; **Remove** removes only the list entry.
5. Choose output dimensions and FPS. Match first video retains the first entry's
   dimensions, rounded up to even pixels where necessary. Other clips are scaled
   with aspect ratio preserved and black bars as needed. The initial FPS is taken
   from the first loaded video and can be changed from 1 to 60.
6. **Export new MP4…** trims a single entry or joins multiple applied ranges.
   Typed fields for the selected clip are applied automatically before export.

Exports use H.264 video and AAC stereo audio, with a common resolution/FPS. Existing
audio is retained/resampled; silent audio is added to silent clips for joining.
Video is re-encoded for accurate boundaries rather than cutting at keyframes.
Only the first video/audio streams are exported; subtitles and extra tracks are
not included. Export quality is CRF 18. Originals and existing output files are
never overwritten, and no source video is deleted. FFmpeg comes from the same
verified bundled encoder used for recording; no ffprobe download is required.

Encoding runs in the background. **Cancel operation** stops FFmpeg and cleans up
temporary files. Closing a busy editor asks whether to cancel; close the editor
before closing SmartScreen. Recording, screenshots and auto-update installation
are blocked/deferred while the editor is open. Exports need extra free disk space
in the destination folder for normalized clips and the joined result. Errors or
cancellation do not publish a partial output file.

## Validation

Run the Python suites with the application's dependencies installed:

```powershell
python -m unittest -v test_build_metadata test_region_selector test_recording test_window_capture test_video_editing
python test_update.py
python -m unittest -v test_video_editor_ui
```

The last test needs a display. It exercises the actual Tk window, file loading,
frame preview, five-second removal, reordering/removal, typed-range export, and
closing. On Linux it explicitly skips when DISPLAY is unavailable. It was run
successfully on an isolated Xorg test display during development.

FFmpeg integration tests verify exact trimmed frame count, duration, audio presence,
mixed-size/FPS joining in order (decoded pixel colors), overwrite protection,
invalid input ranges, cancellation of a running process, concurrent output creation,
cleanup on encoder failure, and original-file hashes. Existing recording, selector,
metadata and updater tests are retained. Native Windows packaging, default-player
launching, and hardware WGC behavior still require Windows checks.

Rebuild using Build_cxFreeze_x64.bat or Build_cxFreeze_x86.bat. Both new editor
modules are explicitly included in cx_Freeze. The build-path correction remains.
Middle-section cutting and a real-time embedded player are deferred to a later version.
