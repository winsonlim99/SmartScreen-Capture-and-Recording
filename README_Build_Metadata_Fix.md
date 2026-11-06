# Build metadata directory fix

The supplied x64 log stops at:

```text
creating SmartScreen_Capture_Recording.egg-info
error: could not create 'SmartScreen_Capture_Recording.egg-info': The system cannot find the path specified
```

This is setuptools metadata generation, before freezing. The log does not identify
the full failing source path, so it cannot establish whether a long path, an
unavailable directory, or another filesystem constraint caused the Windows error.
The existing configuration redirects the EXE but leaves metadata and intermediate
files in the source tree. The corrected setup explicitly places all three beneath
the configured output root:

- `metadata/x64` or `metadata/x86`: setuptools egg-info directory.
- `work/x64` or `work/x86`: intermediate build files.
- `build/SmartScreen_Capture_V1_0` (or `_x86`): frozen application.

The default output root is `%LOCALAPPDATA%\SmartScreenBuild`. Override it if needed
from Command Prompt before running the build helper, for example:

```bat
set "SMARTSCREEN_OUTPUT_ROOT=C:\SSBuild"
Build_cxFreeze_x64.bat
```

Choose a location writable by your account. Also extract the source completely to
a short local folder (for example `C:\SmartScreenSrc`); do not run the helper from
inside a ZIP or an unavailable network folder. No Windows registry change or
administrator mode is required by this correction.

The metadata folder is created before setuptools finalizes `egg_base`. Architecture
directories remain separate, and existing source or release folders are not deleted.
The log now prints the selected metadata directory.

Validation: `python -m unittest -v test_build_metadata` runs the real setuptools
egg-info command using the actual setup options in both x64 and x86 configurations,
with a temporary source folder and a separate output folder containing spaces.
Both produce PKG-INFO outside the source tree. This is not a Windows executable
build; Windows cx_Freeze validation remains required.
