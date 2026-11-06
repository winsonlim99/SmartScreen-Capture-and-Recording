"""Startup-only, verified Current-channel updater for SmartScreen Capture.

The Windows installer/rollback phase runs OUTSIDE the cx_Freeze process, using
Windows PowerShell. Nothing is installed while recording or capturing.
"""
from __future__ import annotations
import hashlib
import json
import logging
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import tempfile
import threading
import time
import uuid

APP_VERSION = '1.0.7'
EXE_NAME = 'SmartScreen_Capture.exe'
PROTECTED = {'config.json', 'update_source.txt', 'capture_v10.log'}
MAX_FILES = 12000


def install_dir():
    import sys
    return Path(sys.executable if getattr(sys, 'frozen', False) else __file__).resolve().parent


def version_tuple(s):
    parts = str(s).split('.')
    if not 1 <= len(parts) <= 4 or any(not p.isdigit() for p in parts):
        raise ValueError('Version must use numeric dotted notation (example 1.0.1)')
    return tuple(int(p) for p in (parts + ['0'] * (4 - len(parts))))


def safe_relative(value):
    if not isinstance(value, str) or '\\' in value or ':' in value or '\x00' in value:
        raise ValueError('Unsafe manifest filename')
    path = PurePosixPath(value)
    if path.is_absolute() or any(p in ('', '.', '..') for p in value.split('/')):
        raise ValueError('Unsafe manifest filename')
    if path.parts[0].lower() in {'.update_stage', '.update_backup'}:
        raise ValueError('Reserved internal path')
    if value.lower() in PROTECTED or path.name.lower() in {'update_source.txt', 'config.json'}:
        raise ValueError('Protected local setting in manifest')
    return path


def validate_manifest(data):
    if not isinstance(data, dict) or data.get('schema') != 1:
        raise ValueError('Unknown release manifest schema')
    version_tuple(data['version'])
    entries = data.get('files')
    if not isinstance(entries, list) or not entries or len(entries) > MAX_FILES:
        raise ValueError('Invalid release file list')
    seen = set()
    for item in entries:
        path = safe_relative(item['path'])
        name = str(path).lower()
        if name in seen:
            raise ValueError('Duplicate manifest path')
        seen.add(name)
        digest = item.get('sha256', '')
        if len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
            raise ValueError('Invalid SHA-256 digest')
        if type(item.get('size')) is not int or item['size'] < 0:
            raise ValueError('Invalid release file size')
    if EXE_NAME.lower() not in seen:
        raise ValueError('Release must contain main EXE')
    return entries


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def current_source(root):
    cfg = root / 'update_source.txt'
    if not cfg.is_file():
        return None
    for line in cfg.read_text(encoding='utf-8-sig').splitlines():
        line = line.strip().strip('"')
        if line and not line.startswith(('#', ';')):
            return Path(line)
    return None


def _check_and_stage(root, notify):
    source = current_source(root)
    if source is None:
        logging.info('Auto-update disabled: update_source.txt missing/empty')
        return
    manifest_path = source / 'version.json'
    try:
        data = json.loads(manifest_path.read_text(encoding='utf-8'))
        files = validate_manifest(data)
        if version_tuple(data['version']) <= version_tuple(APP_VERSION):
            return
        total = sum(item['size'] for item in files)
        free = shutil.disk_usage(root).free
        if free < total * 3 + 300_000_000:
            raise RuntimeError('Insufficient free space to stage and back up update')
        stage_root = root / '.update_stage'
        stage_root.mkdir(exist_ok=True)
        stage = stage_root / ('release-' + uuid.uuid4().hex)
        stage.mkdir()
        try:
            for item in files:
                relative = safe_relative(item['path'])
                src = source.joinpath(*relative.parts)
                dest = stage.joinpath(*relative.parts)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(src, dest)
                if dest.stat().st_size != item['size'] or sha256(dest) != item['sha256']:
                    raise RuntimeError('Downloaded file hash/size mismatch: ' + item['path'])
            (stage / 'version.json').write_text(json.dumps(data, indent=2), encoding='utf-8')
        except Exception:
            shutil.rmtree(stage, ignore_errors=True)
            raise
        notify(data['version'], stage)
    except Exception as exc:
        logging.warning('Startup update check failed; continuing installed version: %s', exc)


def check_background(root, notify):
    """Begin once at startup; server errors never block screenshot/recording."""
    if os.name != 'nt':
        return
    threading.Thread(target=_check_and_stage, args=(Path(root), notify), daemon=True, name='SmartScreenUpdateCheck').start()


def launch_external_updater(root, stage):
    """External PowerShell script waits for this PID to exit before replacing files."""
    root, stage = Path(root), Path(stage)
    script = root / 'updater' / 'Apply_Update.ps1'
    if not script.is_file():
        raise RuntimeError('Bundled updater script missing')
    # Copy script outside app tree so the updater can replace its own installed copy.
    temp_root = Path(tempfile.mkdtemp(prefix='SmartScreenUpdater_'))
    temp_script = temp_root / 'Apply_Update.ps1'
    shutil.copy2(script, temp_script)
    log = root / 'update.log'
    ready = temp_root / 'updater_ready.txt'
    cmd = ['powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File',
           str(temp_script), '-AppDir', str(root), '-StageDir', str(stage), '-ParentPid', str(os.getpid()),
           '-LogFile', str(log), '-ReadyFile', str(ready)]
    flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    process = subprocess.Popen(cmd, cwd=str(temp_root), creationflags=flags, close_fds=True)
    for _ in range(40):  # 4 seconds max; never close app if PowerShell cannot start.
        if ready.exists():
            return
        if process.poll() is not None:
            raise RuntimeError('PowerShell updater exited before starting; check IT restrictions')
        time.sleep(0.1)
    try:
        process.terminate()
    except OSError:
        pass
    raise RuntimeError('PowerShell updater did not acknowledge startup')
