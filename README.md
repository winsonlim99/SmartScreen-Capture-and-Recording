# SmartScreen Capture and Recording

Windows desktop screenshot and MP4 recording utility. Current source: build
1.0.8, based on the supplied 1.0.5 WGC/window-selection archive.
See [embedded player, drag-and-drop and timeline](README_Editor_Player_1_0_8.md)
for the upgraded editor and supported build requirements.
See [selector fix and validation](README_Selector_Fix_1_0_6.md).
For the `.egg-info` directory build error, see the
[metadata build fix](README_Build_Metadata_Fix.md).

Supports global screenshot shortcuts, full-screen or fixed-region recording,
video segmentation, and a shared-folder update channel.

## Develop and build on Windows

Use an interactive Windows desktop and a Python installation matching the target
PC architecture. From this directory:

```powershell
py -m venv .venv
.venv\Scripts\python -m pip install -r requirements-build.txt
.venv\Scripts\python SmartScreen_Capture_V1_0.py
.venv\Scripts\python -m pip install windows-capture==2.0.1
.venv\Scripts\python setup.py build
.venv\Scripts\python make_release.py
```

These commands target x64. For the architecture-specific build and DLL checks, use
`Build_cxFreeze_x64.bat` or `Build_cxFreeze_x86.bat` (their Python paths must match
your installations). Selected Window recording requires x64.
Copy the entire build output directory when distributing the application.
See [original instructions](README.txt), [region selection](README_Fixed_Region.txt),
and [update deployment](README_AutoUpdate.txt).

## Review and validation

See [CODE_REVIEW.md](CODE_REVIEW.md) for fixes, validation, and suggested
improvements. Run the Python regressions with the environment's Python:

```powershell
.venv\Scripts\python -m unittest -v test_region_selector test_recording test_window_capture
.venv\Scripts\python test_update.py
powershell -NoProfile -File updater/Test_Update_Abort.ps1
```

Python checks pass in Linux. The PowerShell regression, Windows desktop behavior,
and cx_Freeze build still require Windows validation.

`patch_update.py` is a historical source-modification helper, not a setup step;
do not run it on the already patched application.
