"""Run after cx_Freeze: create version.json and Release/<version> folder."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
from smart_update import APP_VERSION, safe_relative

ROOT = Path(__file__).resolve().parent
BUILD = ROOT / 'build' / 'SmartScreen_Capture_V1_0'
RELEASE = ROOT / 'Release' / ('SmartScreen_Capture_V' + APP_VERSION.replace('.', '_'))

def build_release():
    if not (BUILD / 'SmartScreen_Capture.exe').exists():
        raise SystemExit('Build executable first using Build_cxFreeze.bat')
    if RELEASE.exists():
        raise SystemExit('Release folder already exists: ' + str(RELEASE))
    RELEASE.parent.mkdir(exist_ok=True)
    RELEASE.mkdir()
    excluded_dirs = {'.update_stage', '.update_backup'}
    excluded_files = {'config.json', 'update_source.txt', 'update.log', 'version.json'}
    entries = []
    for source in sorted(BUILD.rglob('*')):
        if not source.is_file():
            continue
        rel = source.relative_to(BUILD)
        if set(rel.parts) & excluded_dirs or rel.name.lower() in excluded_files:
            continue
        rel_posix = rel.as_posix()
        safe_relative(rel_posix)
        target = RELEASE / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        entries.append({'path': rel_posix, 'size': target.stat().st_size, 'sha256': digest})
    manifest = {'schema': 1, 'version': APP_VERSION, 'files': entries}
    (RELEASE / 'version.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    # Existing installation can be bootstrapped from this release folder.
    for name in ('publish_release.py', 'Publish_Release_To_Current.bat'):
        shutil.copy2(ROOT / name, RELEASE / name)
    print('Created:', RELEASE)
    print('Signed by SHA-256 manifests (integrity, not publisher authenticity):', len(entries), 'files')
    return RELEASE

if __name__ == '__main__':
    build_release()
