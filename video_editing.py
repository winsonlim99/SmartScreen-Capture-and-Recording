"""Local video editing using the existing FFmpeg executable; originals are read-only."""
from dataclasses import dataclass
from pathlib import Path
import io
import math
import os
import re
import subprocess
import tempfile
import threading

from PIL import Image


class EditCancelled(RuntimeError):
    pass


def run_ffmpeg(executable, args, cancel=None):
    if cancel is not None and cancel.is_set():
        raise EditCancelled('Editing cancelled; originals unchanged.')
    process = subprocess.Popen([str(executable), '-hide_banner', '-nostdin', *args],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    try:
        while True:
            try:
                stdout, stderr = process.communicate(timeout=0.2)
                break
            except subprocess.TimeoutExpired:
                if cancel is not None and cancel.is_set():
                    raise EditCancelled('Editing cancelled; originals unchanged.')
        return process.returncode, stdout, stderr.decode('utf-8', errors='replace')
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate()


@dataclass(frozen=True)
class VideoInfo:
    duration: float
    width: int
    height: int
    fps: float
    audio: bool


@dataclass(frozen=True)
class Clip:
    path: str
    start: float
    end: float


def probe_video(executable, path, cancel=None):
    path = Path(path).resolve()
    if not path.is_file():
        raise ValueError('Choose an existing local video file.')
    # -i alone reports metadata and exits without creating any output.
    _, _, report = run_ffmpeg(executable, ['-protocol_whitelist', 'file,pipe', '-i', str(path)], cancel)
    duration = re.search(r'Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)', report)
    stream = next((line for line in report.splitlines() if 'Stream #' in line and 'Video:' in line), '')
    dimensions = re.search(r'\b(\d{2,})x(\d{2,})\b', stream)
    fps = re.search(r'(\d+(?:\.\d+)?)\s+fps\b', stream)
    if not duration or not dimensions:
        raise ValueError('Cannot read video duration/dimensions. Choose a playable video file.')
    h, m, s = map(float, duration.groups())
    seconds = h * 3600 + m * 60 + s
    if seconds <= 0 or not math.isfinite(seconds):
        raise ValueError('Video has no usable duration.')
    return VideoInfo(seconds, *map(int, dimensions.groups()),
                     float(fps.group(1)) if fps else 30.0, 'Audio:' in report)


def preview_frame(executable, path, position, cancel=None):
    code, data, error = run_ffmpeg(executable, [
        '-v', 'error', '-protocol_whitelist', 'file,pipe', '-ss', str(max(0, position)),
        '-i', str(Path(path).resolve()), '-map', '0:v:0', '-frames:v', '1',
        '-vf', 'scale=640:360:force_original_aspect_ratio=decrease',
        '-f', 'image2pipe', '-c:v', 'png', 'pipe:1'], cancel)
    if code or not data:
        raise RuntimeError('Unable to preview this position. ' + error[-500:])
    with Image.open(io.BytesIO(data)) as image:
        return image.convert('RGB').copy()


def export_video(executable, clips, output, size, fps, cancel=None, progress=lambda text: None):
    """Trim each clip precisely, normalize video/audio, and concatenate in order."""
    cancel = cancel or threading.Event()
    if not clips:
        raise ValueError('Add at least one video.')
    width, height = map(int, size)
    if width < 2 or height < 2 or width % 2 or height % 2:
        raise ValueError('Output dimensions must be positive even numbers.')
    if not 1 <= fps <= 60 or not math.isfinite(fps):
        raise ValueError('Output FPS must be between 1 and 60.')
    output = Path(output).resolve()
    if output.suffix.lower() != '.mp4':
        raise ValueError('Use an .mp4 filename for the exported video.')
    if output.exists() or output in [Path(c.path).resolve() for c in clips]:
        raise ValueError('Choose a new output filename; existing files cannot be overwritten.')
    if not output.parent.is_dir():
        raise ValueError('Output folder does not exist.')
    infos = []
    for clip in clips:
        info = probe_video(executable, clip.path, cancel)
        if not all(math.isfinite(v) for v in (clip.start, clip.end)) or not 0 <= clip.start < clip.end <= info.duration + 0.02:
            raise ValueError('Each clip needs 0 ≤ start < end ≤ video duration.')
        infos.append(info)
    expected = sum(c.end - c.start for c in clips)
    with tempfile.TemporaryDirectory(prefix='SmartScreenEdit_', dir=output.parent) as directory:
        temp = Path(directory)
        for index, (clip, info) in enumerate(zip(clips, infos)):
            progress(f'Preparing clip {index + 1} of {len(clips)}…')
            args = ['-v', 'error', '-protocol_whitelist', 'file,pipe', '-ss', str(clip.start), '-i', str(Path(clip.path).resolve())]
            if not info.audio:
                args += ['-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=stereo']
            args += ['-t', str(clip.end - clip.start), '-map', '0:v:0', '-map', '0:a:0' if info.audio else '1:a:0',
                     '-vf', f'scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps}',
                     '-c:v', 'libx264', '-preset', 'fast', '-crf', '18', '-pix_fmt', 'yuv420p',
                     '-af', 'aresample=async=1:first_pts=0,apad', '-c:a', 'aac', '-ar', '48000', '-ac', '2',
                     '-video_track_timescale', '90000', '-movflags', '+faststart', str(temp / f'{index}.mp4')]
            code, _, error = run_ffmpeg(executable, args, cancel)
            if code:
                raise RuntimeError('Clip export failed: ' + error[-1500:])
        progress('Joining clips and checking output…')
        (temp / 'clips.txt').write_text(''.join(f"file '{i}.mp4'\n" for i in range(len(clips))), encoding='utf-8')
        result = temp / 'result.mp4'
        code, _, error = run_ffmpeg(executable, ['-v', 'error', '-f', 'concat', '-safe', '1', '-i', str(temp / 'clips.txt'),
                                               '-c', 'copy', '-movflags', '+faststart', str(result)], cancel)
        if code:
            raise RuntimeError('Join failed: ' + error[-1500:])
        actual = probe_video(executable, result, cancel)
        if abs(actual.duration - expected) > max(0.5, len(clips) * 2 / fps):
            raise RuntimeError('Export duration check failed; no output was saved.')
        if cancel.is_set():
            raise EditCancelled('Editing cancelled; originals unchanged.')
        # Reserve only after successful export. O_EXCL protects files created
        # while editing; never replace an existing user file.
        fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)
        os.close(fd)
        try:
            os.replace(result, output)
        except Exception:
            output.unlink()
            raise
    return str(output)
