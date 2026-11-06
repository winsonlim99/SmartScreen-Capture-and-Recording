"""Validate cx_Freeze output, and add missing *matching interpreter* NumPy binary DLLs.

This is a build-time packaging check, not a replacement for end-to-end Windows testing.
"""
import os,sys,struct,shutil
from pathlib import Path
from build_paths import BUILD
ROOT=Path(__file__).resolve().parent
arch=os.getenv('SMARTSCREEN_BUILD_ARCH','x64').lower()
expected=32 if arch=='x86' else 64
if struct.calcsize('P')*8 != expected:
    raise SystemExit(f'Wrong architecture: expected {expected}-bit')
build=BUILD
exe=build/'SmartScreen_Capture.exe'
if not exe.is_file(): raise SystemExit(f'Missing exe: {exe}. cx_Freeze build did not finish.')
try:
    import numpy
except Exception as exc:
    raise SystemExit(f'NumPy cannot import in this interpreter: {sys.executable}: {exc}') from exc
np_dir=Path(numpy.__file__).resolve().parent
src_libs=np_dir.parent/'numpy.libs'
if not src_libs.is_dir():
    print(f'Note: no numpy.libs beside {np_dir}; wheel may use another DLL layout')
else:
    target=build/'lib'/'numpy.libs'
    target.mkdir(parents=True,exist_ok=True)
    copied=0
    for src in src_libs.iterdir():
        if src.is_file():
            dst=target/src.name
            if not dst.exists() or dst.stat().st_size!=src.stat().st_size:
                shutil.copy2(src,dst)
                copied+=1
            if dst.stat().st_size!=src.stat().st_size:
                raise SystemExit(f'Incomplete numpy DLL: {dst}')
    print(f'NumPy binary dependencies verified ({copied} repaired) from: {src_libs}')
# Detect packaged DLL references only by existence; do not mix x86 and x64 installations.
for f in (build/'lib'/'numpy.libs').glob('*.dll'):
    print('Verified:',f.name, f.stat().st_size, 'bytes')
print('Build verification complete:',exe)
