# Review of imported version 1.0.1

## Fix status

The five findings below have been addressed after the initial review:

- Updater tracks backup ownership and installation state. Aborts before copying
  preserve earlier backups and do not restart the application. A healthy update
  is no longer rolled back if post-success cleanup fails.
- Screenshot delay respects the checkbox and ignores invalid disabled input.
- FFmpeg probes a disposable file and writes only captured frames to recordings.
- A monotonic recording timeline repeats the previous captured frame for missed
  fixed-FPS slots, retaining elapsed timing across segment changes.
- Updater tests explicitly exercise both equal and newer release versions.

Also removed the blocking ten-second GUI close wait and prevented double counting
a completed segment when stopping during rollover.

Validation: six `test_recording` unittest cases pass, including real FFmpeg and
OpenCV MP4 encoding/decoding, delay behavior, slow capture and segment timing.
`python test_update.py` now passes, including corrupt-content rejection.
`updater/Test_Update_Abort.ps1` covers existing backups, invalid schema and invalid
hashes; it is supplied for Windows and has not been executed in this Linux environment.
Windows GUI, packaging and end-to-end rollback remain unverified.

The original findings and initial validation are retained below as review history.

## Findings, in priority order

1. **High: an aborted update can erase a previous recovery backup.**
   `updater/Apply_Update.ps1:34` throws when `.update_backup` already exists,
   but its catch block at lines 75–96 subsequently deletes that directory at
   line 94, even though this invocation did not create it. The same cleanup is
   reachable after earlier validation failures. This destroys recovery data.
   Track whether this invocation owns the backup and whether installation began;
   preserve pre-existing backups and avoid rollback/restart before installation.
   Found by code inspection; PowerShell execution was not available in this check.

2. **Medium: the Delay checkbox does not disable screenshot delay.**
   `SmartScreen_Capture_V1_0.py:976` overwrites the checkbox value with
   `args['delay'] > 0`. A disabled checkbox with the default three seconds still
   waits three seconds. A direct invocation of `capture_now`, intercepting only
   worker dispatch, confirmed `use_delay=False` becomes `True`.
   Preserve the checkbox value when deriving effective delay; do not require a
   valid delay entry when delay is disabled.

3. **Medium: every FFmpeg segment starts with a synthetic black frame.**
   `SmartScreen_Capture_V1_0.py:160` writes its encoder probe into the real output.
   Encoding ten white frames and decoding the MP4 produced eleven frames: the
   first was black and the last white. This affects the start and each rollover.
   Probe into a temporary output, or initialize with the first actual capture.

4. **Medium: slow capture produces video shorter than elapsed recording time.**
   The worker writes one frame per capture at fixed encoder FPS
   (`SmartScreen_Capture_V1_0.py:1982` and lines 2049–2051). If the machine sustains
   five captures/second while configured for ten, one minute becomes about thirty
   seconds of playback. There is no timestamp correction or frame duplication.
   Use monotonic timestamps to preserve elapsed duration and report effective FPS
   or overload to the operator. This follows from the scheduling and encoding
   logic; hardware timing tests were not run.

5. **Medium: the supplied updater test always fails at its staging assertion.**
   `test_update.py:39` expects staging of version 1.0.1, while
   `smart_update.APP_VERSION` is already 1.0.1. The updater correctly skips it.
   Use an explicitly older installed-version fixture and independently test the
   equal-version skip. The original test failed as supplied; running the same
   test with APP_VERSION temporarily patched in memory to 1.0.0 passed, including
   publishing, preservation of local settings, and rejection of corrupt content.

## Validation performed

- Parsed all eight top-level Python files successfully without executing helpers
  that modify source or publish releases.
- Installed keyboard, mss, imageio, imageio-ffmpeg and opencv-python in an external
  workspace virtual environment with existing Pillow and NumPy.
- Used the real RecordingWriter with FFmpeg/H.264, finalized an MP4 and decoded
  its frames. This verifies the Linux encoder path and reproduces the black frame.
- Ran `python test_update.py`: failed at the same-version fixture described above.
- Ran that test again with only the installed-version constant patched in memory:
  `UPDATE_TESTS_PASS`. This is diagnostic evidence, not a pass of the original test.
- No Windows GUI, keyboard hook, multi-monitor/DPI, taskbar, PowerShell rollback,
  or Windows cx_Freeze executable validation has been performed.

## Suggested improvements

- Fix backup ownership first and add Windows integration tests for failures before
  copying, during copying, on startup timeout, and with a pre-existing backup.
- Add automated regression coverage for delay-disabled captures, actual first
  video frames, slow capture timing, rollover, and low-disk handling.
- Use a signed manifest or signed release in addition to SHA-256. A hash supplied
  alongside a file detects corruption but does not authenticate its publisher.
  Restrict write access to the release share in the meantime.
- Pin validated dependency versions for repeatable builds and exercise the frozen
  executable on Windows CI. Current requirements specify mostly unbounded versions.
- Move encoder startup testing off the live recording output; verify output by
  decoding frames, including the OpenCV fallback, rather than file size alone.
- Remove the historical `patch_update.py` in a separate cleanup: rerunning it adds
  duplicate methods/startup callbacks to source that already contains the patch.
- Avoid blocking Tk for up to ten seconds in `_on_close` via `join`; request stop
  and poll completion using `after`, keeping finalization progress responsive.

Before equipment deployment, validate a packaged build on a nonproduction Windows
PC with the intended monitor layout, permissions, encoders and update share.
