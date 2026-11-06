"""Architecture-isolated short output paths to avoid Windows MAX_PATH failures."""
from pathlib import Path
import os

ROOT = Path(__file__).resolve().parent
ARCH = os.environ.get("SMARTSCREEN_BUILD_ARCH", "x64").lower()
if ARCH not in ("x86", "x64"):
    raise ValueError("SMARTSCREEN_BUILD_ARCH must be x86 or x64")
# Keep the frozen EXE and releases outside deeply nested project paths.
# The default is writable for standard Windows user accounts.
BASE = Path(os.environ.get("SMARTSCREEN_OUTPUT_ROOT") or
            (Path(os.environ.get("LOCALAPPDATA") or str(Path.home())) / "SmartScreenBuild"))
BUILD = BASE / "build" / ("SmartScreen_Capture_V1_0_x86" if ARCH == "x86" else "SmartScreen_Capture_V1_0")
BUILD_WORK = BASE / "work" / ARCH
METADATA = BASE / "metadata" / ARCH
RELEASE_ROOT = BASE / "Release"
