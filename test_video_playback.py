"""Actual decoder tests. Set SDL_AUDIODRIVER=dummy on audio-less CI hosts."""
import os
from pathlib import Path
import queue
import tempfile
import threading
import time
import unittest

from SmartScreen_Capture_V1_0 import ffmpeg_executable
from video_editing import run_ffmpeg
from video_playback import PreviewPlayer


class PlaybackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.path = Path(cls.directory.name) / 'test video.mp4'
        cls.executable = ffmpeg_executable()
        code, _, error = run_ffmpeg(cls.executable, ['-v', 'error', '-f', 'lavfi', '-i',
            'testsrc2=s=160x120:r=10:d=3', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=3',
            '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-t', '3', str(cls.path)])
        if code:
            raise RuntimeError(error)

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def setUp(self):
        self.player = PreviewPlayer(self.executable)
        self.addCleanup(self.shutdown)

    def shutdown(self):
        self.player.close()
        self.player.thread.join(timeout=5)
        self.assertFalse(self.player.thread.is_alive())

    def frame(self, revision, minimum=0, timeout=6):
        deadline = time.monotonic()+timeout
        while time.monotonic() < deadline:
            try:
                rev, kind, value = self.player.frames.get(timeout=0.05)
            except queue.Empty:
                continue
            if rev != revision:
                continue
            if kind == 'error':
                self.fail(value)
            if kind == 'frame' and value[1] >= minimum:
                return value
        self.fail('No decoded frame for current request')

    def test_embedded_audio_video_plays_then_pauses_and_seeks(self):
        revision = self.player.request(path=str(self.path), position=0, end=2.5, playing=True, volume=0.3)
        started = time.monotonic()
        image, pts = self.frame(revision, minimum=0.5)
        self.assertGreater(image.width, 0)
        self.assertGreaterEqual(time.monotonic()-started, 0.3)
        revision = self.player.request(playing=False, position=1.7)
        _, pts = self.frame(revision)
        self.assertAlmostEqual(pts, 1.7, delta=0.01)
        self.assertTrue(self.player.thread.is_alive())
        revision = self.player.request(playing=True, position=1.5, volume=0)
        _, pts = self.frame(revision, minimum=1.5)
        self.assertGreaterEqual(pts, 1.5)

    def test_latest_seek_wins_and_frame_queue_is_bounded(self):
        for position in (0.3, 1.2, 2.1, 0.7, 1.9):
            revision = self.player.request(path=str(self.path), position=position, end=3, playing=False)
        _, pts = self.frame(revision)
        self.assertAlmostEqual(pts, 1.9, delta=0.01)
        revision = self.player.request(playing=True, position=0)
        # Deliberately leave frames unread, modelling a minimized/unfocused UI.
        threading.Event().wait(0.8)
        self.assertLessEqual(self.player.frames.qsize(), 1)
        _, pts = self.frame(revision)
        self.assertGreater(pts, 0)

    def test_selected_end_stops_playback(self):
        revision = self.player.request(path=str(self.path), position=0, end=0.4, playing=True)
        deadline = time.monotonic()+6
        while time.monotonic() < deadline:
            try:
                rev, kind, value = self.player.frames.get(timeout=0.05)
            except queue.Empty:
                continue
            if kind == 'error':
                self.fail(value)
            if rev == revision and kind == 'ended':
                break
        else:
            self.fail('Selection boundary did not stop playback')
        self.assertFalse(self.player.snapshot()['playing'])


if __name__ == '__main__':
    unittest.main()
