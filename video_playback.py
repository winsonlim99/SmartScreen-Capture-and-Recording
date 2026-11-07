"""Single-owner decoder worker. Tk receives only the newest frame, never a backlog."""
from pathlib import Path
import os
import sys
import queue
import threading
import time

from PIL import Image
from video_editing import EditCancelled, preview_frame


_dll_handles = []


def prepare_player_libraries():
    if os.name == 'nt' and getattr(sys, 'frozen', False) and not _dll_handles:
        root = Path(sys.executable).resolve().parent / 'share' / 'ffpyplayer'
        for library in ('ffmpeg', 'sdl'):
            directory = root / library / 'bin'
            if directory.is_dir() and hasattr(os, 'add_dll_directory'):
                _dll_handles.append(os.add_dll_directory(str(directory)))


class PreviewPlayer:
    def __init__(self, executable):
        self.executable = executable
        self.frames = queue.Queue(maxsize=1)
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._preview_cancel = None
        self._state = dict(path=None, position=0.0, end=0.0, playing=False,
                           volume=1.0, width=640, revision=0, seek=0)
        self.thread = threading.Thread(target=self._run, daemon=True, name='SmartScreenPlayer')
        self.thread.start()

    def request(self, **values):
        with self._lock:
            if 'position' in values or 'path' in values:
                self._state['seek'] += 1
            self._state.update(values)
            self._state['revision'] += 1
            revision = self._state['revision']
            if self._preview_cancel is not None:
                self._preview_cancel.set()
        self._wake.set()
        return revision

    def snapshot(self):
        with self._lock:
            return dict(self._state)

    def _publish(self, revision, kind, payload):
        if self.snapshot()['revision'] != revision or self._stop.is_set():
            return
        try:
            self.frames.get_nowait()
        except queue.Empty:
            pass
        self.frames.put_nowait((revision, kind, payload))

    def close(self):
        self._stop.set()
        with self._lock:
            if self._preview_cancel is not None:
                self._preview_cancel.set()
        self._wake.set()

    def _run(self):
        player = None
        source = None
        last_seek = -1
        last_width = None
        last_pts = 0.0
        native_errors = queue.SimpleQueue()
        opened_at = 0.0
        got_frame = False
        paused_revision = -1
        try:
            while not self._stop.is_set():
                self._wake.clear()
                state = self.snapshot()
                revision = state['revision']
                try:
                    if not state['playing']:
                        if player is not None:
                            old, player = player, None
                            old.close_player()
                            player = None
                            source = None
                        if state['path'] and revision != paused_revision:
                            with self._lock:
                                cancel = self._preview_cancel = threading.Event()
                                if self._state['revision'] != revision:
                                    cancel.set()
                            image = preview_frame(self.executable, state['path'], state['position'], cancel)
                            self._publish(revision, 'frame', (image, state['position']))
                            paused_revision = revision
                        self._wake.wait(0.1)
                        continue
                    if player is None or source != state['path']:
                        if player is not None:
                            old, player = player, None
                            old.close_player()
                        try:
                            prepare_player_libraries()
                            from ffpyplayer.player import MediaPlayer
                        except ImportError as exc:
                            raise RuntimeError('Embedded playback requires the x64 player build (ffpyplayer). Frame preview and export remain available.') from exc
                        native_errors = queue.SimpleQueue()
                        def native_event(selector, value, errors=native_errors):
                            if selector.endswith(':error'):
                                errors.put(f'{selector}: {value}')
                        player = MediaPlayer(str(Path(state['path']).resolve()), callback=native_event,
                            loglevel='warning',
                            ff_opts={'out_fmt': 'rgb24', 'ss': state['position'], 'volume': state['volume']})
                        opened_at, got_frame = time.monotonic(), False
                        source = state['path']
                        last_seek = state['seek']
                        last_pts = state['position']
                        player.set_size(state['width'], -1)
                        last_width = state['width']
                    if last_width != state['width']:
                        player.set_size(state['width'], -1)
                        last_width = state['width']
                    if last_seek != state['seek']:
                        player.seek(state['position'], relative=False, accurate=True)
                        last_seek = state['seek']
                    player.set_volume(state['volume'])
                    try:
                        error = native_errors.get_nowait()
                    except queue.Empty:
                        error = None
                    if error:
                        raise RuntimeError(error)
                    if not got_frame and time.monotonic()-opened_at > 10:
                        raise RuntimeError('Playback did not produce a frame. Try another video or check the audio device.')
                    frame, delay = player.get_frame()
                    if delay == 'eof':
                        with self._lock:
                            if self._state['revision'] == revision:
                                self._state['playing'] = False
                                self._state['position'] = max(0, last_pts)
                        self._publish(revision, 'ended', None)
                        continue
                    if frame is not None:
                        got_frame = True
                        image, pts = frame
                        if pts >= state['end']:
                            with self._lock:
                                if self._state['revision'] == revision:
                                    self._state['playing'] = False
                                    self._state['position'] = max(0, last_pts)
                            self._publish(revision, 'ended', None)
                            continue
                        last_pts = pts
                        pil = Image.frombytes('RGB', image.get_size(), bytes(image.to_bytearray()[0]),
                                              'raw', 'RGB', image.get_linesizes()[0], 1)
                        # get_frame supplies a presentation delay; do not display
                        # early or queue hundreds of decoded frames while unfocused.
                        if isinstance(delay, (int, float)) and delay > 0:
                            self._wake.wait(delay)
                        self._publish(revision, 'frame', (pil, pts))
                    else:
                        self._wake.wait(0.01)
                except EditCancelled:
                    continue
                except Exception as exc:
                    if player is not None:
                        old, player = player, None
                        old.close_player()
                        source = None
                    with self._lock:
                        if self._state['revision'] == revision:
                            self._state['playing'] = False
                    paused_revision = revision
                    self._publish(revision, 'error', str(exc))
                    self._wake.wait(0.1)
        finally:
            if player is not None:
                player.close_player()
