# Build 1.0.6: restore the application after area selection

Based on the user-supplied 1.0.5 WGC cx_Freeze archive. Source, assets and build
helpers were imported; personal config, build logs, bytecode and egg-info were
excluded. The original upload remains available separately.

## Fixes

The old selector saved a restore flag only for Tk state `normal`. On Windows,
a maximized application is `zoomed`, so it withdrew itself for selection but did
not restore itself after right-click. A stale manual-hide flag could also prevent
restoration. The selector now remembers normal/maximized state and restores the
application independently of old hide flags, with the original maximize state.

Both region and window selectors use the same restoration path. Pending minimize
requests are cancelled before selection. Overlapping selectors and screenshot/
recording starts during selection are blocked. Enter/Escape stop event propagation,
and repeated completion callbacks cannot save or destroy the overlay twice.
The region selector now handles window close requests and destroys partially
created overlays on errors. The selected-window status now describes independent
WGC capture rather than incorrectly calling it a visible desktop crop.

Build/update version constants and the About build number are 1.0.6 so the update
channel can distinguish this correction from 1.0.5.

## Validation

- 21 Python unittest cases passed: nine selector callback/session tests, six video
  encoding/timing tests and six WGC wrapper tests.
- Selector tests simulate normal and Windows maximized window states, right-click,
  Enter event bubbling, Escape, window close, no rectangle, screenshot conflicts,
  concurrent selection and failures before/after overlay creation. Negative monitor
  coordinates are checked when storing the selected region.
- Real FFmpeg and OpenCV MP4 encoding/decoding passed; WGC uses a fake event-driven
  capture backend to check copied pixels, errors, closed/minimized windows and
  initial-frame timeout. The pinned windows-capture 2.0.1 wheel was also inspected
  to confirm constructor and callback compatibility; its native code was not run.
- Updater publish/stage/corrupt-content integration tests passed.
- Native Windows GUI/DPI/multi-monitor behavior, WGC hardware capture, PowerShell
  rollback and Windows x64/x86 frozen builds have not been run in Linux.

Reproduce Python checks with installed dependencies:

```powershell
python -m unittest -v test_region_selector test_recording test_window_capture
python test_update.py
```

On Windows, rebuild with the appropriate architecture helper. Test a normal and
maximized main window: select Custom Region, drag a rectangle, right-click, confirm
that SmartScreen returns and Show Area matches the rectangle. Repeat with Enter,
Escape, a tiny/empty selection and a secondary monitor. Record/play a short clip.
Check Selected Window on x64 with the real HMI, including closing/minimizing the
HMI while recording. Keep the full build folder with its bundled dependencies.
