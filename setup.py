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
from build_paths import BUILD, BUILD_WORK, METADATA

ROOT = Path(__file__).resolve().parent
APP_NAME = "SmartScreen Capture & Recording"
APP_VERSION = "1.0.8"
SOURCE = ROOT / "SmartScreen_Capture_V1_0.py"
ICON = ROOT / "assets" / "ASC_Logo.ico"

if os.name != "nt":
    raise SystemExit("Build this portable Windows application on a Windows PC.")

# Prefer a deliberately supplied architecture-matched encoder. A Windows x86
# FFmpeg executable is not guaranteed to be distributed by imageio-ffmpeg.
IS_X86 = os.getenv("SMARTSCREEN_BUILD_ARCH", "").lower() == "x86"
EXPECTED_BITS = 32 if IS_X86 else 64
import struct
if struct.calcsize("P") * 8 != EXPECTED_BITS:
    raise SystemExit(f"Wrong Python architecture: expected {EXPECTED_BITS}-bit for this build")

FFMPEG_EXE = ROOT / "ffmpeg" / "ffmpeg.exe"
if not FFMPEG_EXE.is_file():
    try:
        import imageio_ffmpeg
        FFMPEG_EXE = Path(imageio_ffmpeg.get_ffmpeg_exe()).resolve()
    except (ImportError, RuntimeError, OSError) as exc:
        raise SystemExit(
            "FFmpeg unavailable. For x86, place a compatible 32-bit ffmpeg.exe "
            "in the project's ffmpeg folder, or install a compatible "
            f"imageio-ffmpeg build. Details: {exc}"
        ) from exc

if not FFMPEG_EXE.is_file():
    raise SystemExit(f"FFmpeg executable not found: {FFMPEG_EXE}")
try:
    test = subprocess.run([str(FFMPEG_EXE), "-version"], check=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          timeout=15)
except (OSError, subprocess.SubprocessError) as exc:
    raise SystemExit(f"Bundled FFmpeg cannot run under this Windows system: {exc}") from exc

# Check PE header architecture, rather than trusting a filename or version line.
def pe_machine(path):
    import struct as _struct
    with open(path, "rb") as f:
        if f.read(2) != b"MZ": return None
        f.seek(0x3c)
        offset = _struct.unpack("<I", f.read(4))[0]
        f.seek(offset)
        if f.read(4) != b"PE\0\0": return None
        return _struct.unpack("<H", f.read(2))[0]

machine = pe_machine(FFMPEG_EXE)
expected_machine = 0x014c if IS_X86 else 0x8664
if machine != expected_machine:
    raise SystemExit(
        f"FFmpeg architecture mismatch: {FFMPEG_EXE} has PE machine "
        f"{machine!r}, expected {expected_machine:#06x} "
        f"({'x86' if IS_X86 else 'x64'})."
    )

include_files = [
    (str(ROOT / "assets"), "assets"),
    (str(FFMPEG_EXE), "ffmpeg/ffmpeg.exe"),
    (str(ROOT / "updater"), "updater"),
]

# Tk drag-and-drop uses native Tcl/DLL files that package discovery alone may
# omit. Preserve the package-relative directory used by tkinterdnd2._require.
import tkinterdnd2
import tkinter
if tkinter.TclVersion >= 9:
    raise SystemExit('The bundled drag-and-drop extension requires Tcl/Tk 8.6. Use the supported Windows Python 3.13 installer with Tcl/Tk 8.6.')
include_files.append((str(Path(tkinterdnd2.__file__).parent / 'tkdnd'),
                      'lib/tkinterdnd2/tkdnd'))
if not IS_X86:
    import ffpyplayer
    from ffpyplayer.player import MediaPlayer  # fail build if native dependencies cannot load
    for directory in ffpyplayer.dep_bins:
        native = Path(directory)
        include_files.append((str(native), 'share/ffpyplayer/' + native.parent.name + '/bin'))

build_options = {
    "packages": [
        "tkinter", "PIL", "keyboard", "mss", "numpy",
        "imageio", "smart_update", "wgc_window_capture", "video_editor", "video_editing", "video_playback", "video_timeline", "tkinterdnd2",
    ],
    "includes": ["PIL.ImageTk", "mss.tools", "imageio.plugins.ffmpeg", "smart_update"],
    "include_files": include_files,
    "excludes": ["pytest", "unittest", "test", "matplotlib", "IPython"],
    "include_msvcr": True,
    "zip_include_packages": [],
    "zip_exclude_packages": ["*"],
    "build_exe": str(BUILD),
}

if not IS_X86:
    build_options['packages'].append('ffpyplayer')
    build_options['includes'].append('ffpyplayer.player')
else:
    # No Python 3.13 win32 ffpyplayer wheel: retain trim/join and frame preview.
    build_options['excludes'].append('ffpyplayer')

# OpenCV and the imageio-ffmpeg Python helper are optional; recording can use
# imageio and the verified bundled ffmpeg executable directly.
for pkg in (("cv2", "imageio_ffmpeg") if IS_X86 else ("cv2", "imageio_ffmpeg", "windows_capture")):
    try:
        __import__(pkg)
        build_options["packages"].append(pkg)
    except ImportError:
        print(f"Optional package {pkg} unavailable; continuing without it")

if not IS_X86:
    try:
        import windows_capture
    except ImportError as exc:
        raise SystemExit("x64 WGC dependency missing: run C:\\Python313-64\\python.exe -m pip install windows-capture==2.0.1") from exc

# setuptools runs egg_info during build_exe. Keep that output outside the source
# tree as well: long/nested Windows source paths can fail before freezing starts.
# egg_base must already exist when setuptools finalizes its options.
try:
    METADATA.mkdir(parents=True, exist_ok=True)
except OSError as exc:
    raise SystemExit(
        f"Cannot create build metadata directory: {METADATA}\n"
        "Set SMARTSCREEN_OUTPUT_ROOT to a short, writable local folder and retry.\n"
        f"Details: {exc}"
    ) from exc
print(f"Build metadata directory: {METADATA}", flush=True)

setup(
    name=APP_NAME,
    version=APP_VERSION,
    description="SmartScreen screenshot and recording utility",
    options={
        "build": {"build_base": str(BUILD_WORK)},
        "egg_info": {"egg_base": str(METADATA)},
        "build_exe": build_options,
    },
    executables=[Executable(
        script=str(SOURCE),
        base="gui",
        target_name="SmartScreen_Capture.exe",
        icon=str(ICON),
        shortcut_name=APP_NAME,
        shortcut_dir="DesktopFolder",
    )],
)
