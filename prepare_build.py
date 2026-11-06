"""Clean the selected architecture's build output only; avoid mixed DLLs."""
from pathlib import Path
import os, shutil, struct, sys
from build_paths import BUILD
ROOT = Path(__file__).resolve().parent
arch = os.getenv('SMARTSCREEN_BUILD_ARCH', 'x64').lower()
expected = 32 if arch == 'x86' else 64
actual = struct.calcsize('P') * 8
if actual != expected:
    raise SystemExit(f'ERROR: expected {expected}-bit Python, got {actual}-bit: {sys.executable}')
folder = BUILD
if folder.exists():
    print(f'Removing previous {arch} build: {folder}', flush=True)
    try: shutil.rmtree(folder)
    except OSError as exc: raise SystemExit(f'Cannot clear build folder. Close the EXE and release file locks: {exc}')
print(f'Clean {arch} build target: {folder}', flush=True)
