"""cx_Freeze Windows build for SmartScreen Capture & Recording V1.0.

Run on Windows (the same architecture as your target PCs):
    py -m pip install -r requirements-build.txt
    py setup.py build

This includes the FFmpeg executable delivered by the installed imageio-ffmpeg
Windows wheel. It does NOT download files at runtime on equipment PCs.
"""
from pathlib import Path
import os
import subprocess
import sys
from cx_Freeze import setup, Executable

ROOT = Path(__file__).resolve().parent
APP_NAME = "SmartScreen Capture & Recording"
APP_VERSION = "1.0.1"
SOURCE = ROOT / "SmartScreen_Capture_V1_0.py"
ICON = ROOT / "assets" / "ASC_Logo.ico"

if os.name != "nt":
    raise SystemExit("Build this portable Windows application on a Windows PC.")

try:
    import imageio_ffmpeg
    FFMPEG_EXE = Path(imageio_ffmpeg.get_ffmpeg_exe()).resolve()
except (ImportError, RuntimeError, OSError) as exc:
    raise SystemExit(f"imageio-ffmpeg Windows package is required: {exc}") from exc

if not FFMPEG_EXE.is_file() or FFMPEG_EXE.suffix.lower() != ".exe":
    raise SystemExit(f"Expected Windows ffmpeg.exe, received: {FFMPEG_EXE}")

# Do not silently ship an unusable or wrong-platform encoder.
try:
    subprocess.run([str(FFMPEG_EXE), "-version"], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=15)
except (OSError, subprocess.SubprocessError) as exc:
    raise SystemExit(f"FFmpeg self-test failed: {exc}") from exc

include_files = [
    (str(ROOT / "assets"), "assets"),
    (str(FFMPEG_EXE), "ffmpeg/ffmpeg.exe"),
    (str(ROOT / "updater"), "updater"),
]

build_options = {
    "packages": [
        "tkinter", "PIL", "keyboard", "mss", "numpy",
        "imageio", "imageio_ffmpeg", "cv2", "smart_update",
    ],
    "includes": ["PIL.ImageTk", "mss.tools", "imageio.plugins.ffmpeg", "smart_update"],
    "include_files": include_files,
    "excludes": ["pytest", "unittest", "test", "matplotlib", "IPython"],
    "include_msvcr": True,
    "zip_include_packages": [],
    "zip_exclude_packages": ["*"],
    "build_exe": str(ROOT / "build" / "SmartScreen_Capture_V1_0"),
}

setup(
    name=APP_NAME,
    version=APP_VERSION,
    description="SmartScreen screenshot and recording utility",
    options={"build_exe": build_options},
    executables=[Executable(
        script=str(SOURCE),
        base="gui",
        target_name="SmartScreen_Capture.exe",
        icon=str(ICON),
        shortcut_name=APP_NAME,
        shortcut_dir="DesktopFolder",
    )],
)
