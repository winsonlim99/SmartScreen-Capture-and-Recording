"""Headless regression tests: python -m unittest -v test_recording."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import imageio.v2 as imageio
import numpy as np
import SmartScreen_Capture_V1_0 as app


class RecordingTests(unittest.TestCase):
    def test_disabled_delay_reaches_worker_without_wait(self):
        obj = app.ScreenshotApp.__new__(app.ScreenshotApp)
        obj._screenshot_running = False
        obj._capture_options = lambda: dict(delay=3, use_delay=False)
        obj.capture_btn = SimpleNamespace(config=lambda **kw: None)
        obj.hide_during_capture_var = SimpleNamespace(get=lambda: False)
        with patch.object(app.threading, 'Thread') as thread:
            obj.capture_now()
        options = thread.call_args.kwargs['args'][0]
        self.assertFalse(options['use_delay'])

    def test_disabled_delay_does_not_parse_disabled_input(self):
        value = lambda v: SimpleNamespace(get=lambda: v)
        obj = app.ScreenshotApp.__new__(app.ScreenshotApp)
        obj.save_as_var = value('test')
        obj.save_dir_var = value('folder')
        obj.use_delay_var = value(False)
        obj.delay_seconds_var = value('invalid')
        obj.use_monitor_select_var = value(False)
        obj.monitor_list_var = value('all')
        obj._monitors_cache = []
        obj.scale_var = value('100%')
        self.assertEqual(obj._capture_options()['delay'], 0)

    def check_video(self, force_opencv=False):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'recording.mp4'
            with patch.object(app, '_imageio_available', not force_opencv):
                writer = app.RecordingWriter(path, 10, (320, 240))
            if not force_opencv:
                self.assertTrue(writer.backend.startswith('FFmpeg'))
            else:
                self.assertTrue(writer.backend.startswith('OpenCV'))
            try:
                for _ in range(10):
                    writer.write(np.full((240, 320, 3), 255, dtype=np.uint8))
            finally:
                writer.close()
            reader = imageio.get_reader(path)
            try:
                frames = list(reader.iter_data())
            finally:
                reader.close()
            self.assertEqual(len(frames), 10)
            self.assertGreater(float(frames[0].mean()), 245)

    def test_ffmpeg_has_no_extra_black_frame(self):
        self.check_video()

    def test_opencv_fallback_encodes_real_frames(self):
        self.check_video(force_opencv=True)

    def test_slow_capture_preserves_duration_and_previous_pixels(self):
        frames = []
        timeline = app.RecordingTimeline(SimpleNamespace(write=frames.append), 10)
        timeline.write('first', 100.0)
        timeline.write('second', 100.5)
        timeline.write('third', 101.0)
        self.assertEqual(len(frames), 11)
        self.assertEqual(frames[:5], ['first'] * 5)
        self.assertEqual(frames[5:10], ['second'] * 5)
        self.assertEqual(frames[-1], 'third')

    def test_rollover_preserves_timeline(self):
        first, second = [], []
        timeline = app.RecordingTimeline(SimpleNamespace(write=first.append), 10)
        timeline.write('first', 0.0)
        timeline.writer = SimpleNamespace(write=second.append)
        timeline.write('second', 0.3)
        self.assertEqual(first + second, ['first', 'first', 'first', 'second'])


if __name__ == '__main__':
    unittest.main()
