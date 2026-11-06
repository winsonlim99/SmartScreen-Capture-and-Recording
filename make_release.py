"""Create a verified, versioned release from the cx_Freeze build.

Handles long Windows project paths (\\?\\ extended-length paths) and removes an
incomplete release on failure. Existing releases are never overwritten.
"""
from pathlib import Path
import hashlib
import json
import os
import shutil
import sys
from smart_update import APP_VERSION, safe_relative
from build_paths import BUILD, RELEASE_ROOT

ROOT = Path(__file__).resolve().parent
ARCH_SUFFIX = "_x86" if os.getenv("SMARTSCREEN_BUILD_ARCH") == "x86" else ""
RELEASE = RELEASE_ROOT / ("SmartScreen_Capture_V" + APP_VERSION.replace(".", "_") + ARCH_SUFFIX)


def fs_path(path):
    """Return an absolute OS path with Windows long-path support."""
    absolute = os.path.abspath(os.fspath(path))
    if os.name == "nt":
        if absolute.startswith("\\\\?\\"):
            return absolute
        if absolute.startswith("\\\\"):
            return "\\\\?\\UNC\\" + absolute[2:]
        return "\\\\?\\" + absolute
    return absolute


def copy_file(source, target):
    try:
        os.makedirs(fs_path(target.parent), exist_ok=True)
        shutil.copy2(fs_path(source), fs_path(target))
    except OSError as exc:
        raise OSError(
            f"Failed copying:\n  FROM: {source}\n  TO:   {target}\n"
            f"  Reason: {exc}\n"
            "If this persists, extract the source to C:\\SmartScreenBuild "
            "and rebuild from that short location."
        ) from exc


def sha256_file(path):
    digest = hashlib.sha256()
    with open(fs_path(path), "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_release():
    if not os.path.isfile(fs_path(BUILD / "SmartScreen_Capture.exe")):
        raise SystemExit(
            "Missing build\\SmartScreen_Capture_V1_0\\SmartScreen_Capture.exe. "
            "Run 'py setup.py build' first."
        )
    if os.path.exists(fs_path(RELEASE)):
        raise SystemExit(
            "Release already exists: " + str(RELEASE) + "\n"
            "Do not overwrite published releases. Remove only an incomplete "
            "test release, or increment APP_VERSION."
        )

    excluded_dirs = {".update_stage", ".update_backup"}
    excluded_files = {"config.json", "update_source.txt", "update.log", "version.json"}
    entries = []
    copied = 0
    try:
        os.makedirs(fs_path(RELEASE), exist_ok=False)
        # os.walk supports extended-length paths on Windows. Avoid pathlib.rglob
        # on Windows setups whose path enumeration still runs into MAX_PATH.
        for current, dirs, files in os.walk(fs_path(BUILD)):
            dirs[:] = sorted(d for d in dirs if d not in excluded_dirs)
            for filename in sorted(files):
                if filename.lower() in excluded_files:
                    continue
                src = Path(current) / filename
                rel = Path(os.path.relpath(os.fspath(src), fs_path(BUILD)))
                rel_posix = rel.as_posix()
                safe_relative(rel_posix)
                dst = RELEASE / rel
                copy_file(src, dst)
                entries.append({
                    "path": rel_posix,
                    "size": os.path.getsize(fs_path(dst)),
                    "sha256": sha256_file(dst),
                })
                copied += 1
                if copied % 100 == 0:
                    print(f"Copied {copied} files...", flush=True)

        manifest = {"schema": 1, "version": APP_VERSION, "files": entries}
        with open(fs_path(RELEASE / "version.json"), "w", encoding="utf-8") as handle:
            json.dump(manifest, handle, indent=2)
        for name in ("publish_release.py", "Publish_Release_To_Current.bat"):
            copy_file(ROOT / name, RELEASE / name)
    except Exception:
        # Never leave a half-populated directory that blocks the next build.
        shutil.rmtree(fs_path(RELEASE), ignore_errors=True)
        raise

    print(f"Release created: {RELEASE}")
    print(f"SHA-256 manifest: {len(entries)} application files")
    return RELEASE


if __name__ == "__main__":
    try:
        build_release()
    except OSError as exc:
        print(f"RELEASE BUILD ERROR:\n{exc}", file=sys.stderr)
        raise SystemExit(1) from exc
