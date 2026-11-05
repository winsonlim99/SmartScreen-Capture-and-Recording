"""Publish the folder containing this script to sibling ../../Current.

Expected: SERVER/SmartScreen/Release/SmartScreen_Capture_V1_0_1/this-script
Output:   SERVER/SmartScreen/Current
"""
from pathlib import Path
import hashlib
import json
import os
import shutil
import sys

HERE = Path(__file__).resolve().parent

def run():
    if HERE.parent.name.lower() != 'release':
        raise SystemExit('Run from a release subfolder under SERVER\\Release\\<version>')
    server = HERE.parent.parent
    current = server / 'Current'
    staged = server / 'Current_New'
    older = server / 'Current_Old'
    if staged.exists() or older.exists():
        raise SystemExit('Current_New or Current_Old already exists. Review/clean manually before publishing.')
    manifest = json.loads((HERE/'version.json').read_text(encoding='utf-8'))
    from_types = manifest.get('files', [])
    if not from_types or manifest.get('schema') != 1:
        raise SystemExit('Missing or invalid manifest')
    # Use local validation without relying on Python availability on equipment PCs.
    from pathlib import PurePosixPath
    seen = set()
    for item in from_types:
        name = item['path']
        pp = PurePosixPath(name)
        if pp.is_absolute() or '\\' in name or ':' in name or '..' in pp.parts or name.lower() in seen:
            raise SystemExit('Unsafe manifest path: '+name)
        seen.add(name.lower())
        src = HERE.joinpath(*pp.parts)
        if not src.is_file() or src.stat().st_size != item['size']:
            raise SystemExit('Release file missing or wrong size: '+name)
        sha = hashlib.sha256(src.read_bytes()).hexdigest()
        if sha != item['sha256']:
            raise SystemExit('Release hash mismatch: '+name)
    staged.mkdir()
    swapped = False
    try:
        for item in from_types:
            rel = PurePosixPath(item['path'])
            dst = staged.joinpath(*rel.parts)
            dst.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(HERE.joinpath(*rel.parts),dst)
            if hashlib.sha256(dst.read_bytes()).hexdigest() != item['sha256']:
                raise RuntimeError('Staged file verification failed: '+item['path'])
        shutil.copy2(HERE/'version.json',staged/'version.json')
        if current.exists():
            current.rename(older)
            swapped = True
        staged.rename(current)
        print('PUBLISHED version',manifest['version'],'to',current)
        if older.exists():
            print('Previous Current retained at',older)
    except Exception:
        if swapped and not current.exists() and older.exists():
            older.rename(current)
        if staged.exists(): shutil.rmtree(staged)
        raise

if __name__ == '__main__':
    try: run()
    except Exception as exc:
        print('Publish FAILED:',exc)
        sys.exit(1)
