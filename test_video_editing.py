import hashlib
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

import numpy as np
import imageio.v2 as imageio
from SmartScreen_Capture_V1_0 import ffmpeg_executable
from video_editing import Clip, EditCancelled, export_video, probe_video, preview_frame, run_ffmpeg


class VideoEditingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ffmpeg = ffmpeg_executable()
        if not cls.ffmpeg:
            raise RuntimeError('FFmpeg is required to run video editing integration tests.')

    def setUp(self):
        self.directory = self.enterContext(tempfile.TemporaryDirectory())
        self.root = Path(self.directory)
        self.red = self.make_video('red.mp4', 'red', '160x120', 10, audio=True)
        self.blue = self.make_video('blue.mp4', 'blue', '240x160', 15)
        self.hashes = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in (self.red, self.blue)}
        self.addCleanup(self.check_originals)

    def make_video(self, name, color, size, fps, audio=False):
        path = self.root / name
        args = ['-v', 'error', '-f', 'lavfi', '-i', f'color=c={color}:s={size}:r={fps}:d=2']
        if audio:
            args += ['-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000:duration=2']
        args += ['-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-t', '2', str(path)]
        code, _, error = run_ffmpeg(self.ffmpeg, args)
        self.assertEqual(code, 0, error)
        return path

    def check_originals(self):
        for path, digest in self.hashes.items():
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest)

    def test_trim_precise_duration_and_preserve_audio(self):
        output = self.root / 'trimmed.mp4'
        export_video(self.ffmpeg, [Clip(str(self.red), 0.5, 1.5)], output, (160, 120), 10)
        info = probe_video(self.ffmpeg, output)
        self.assertAlmostEqual(info.duration, 1, delta=0.15)
        self.assertTrue(info.audio)
        reader = imageio.get_reader(output)
        try:
            frames = list(reader.iter_data())
        finally:
            reader.close()
        self.assertEqual(len(frames), 10)

    def test_join_mixed_dimensions_fps_and_audio_in_requested_order(self):
        output = self.root / 'joined.mp4'
        export_video(self.ffmpeg, [Clip(str(self.blue), 0, 1), Clip(str(self.red), 0, 1)], output, (320, 240), 10)
        info = probe_video(self.ffmpeg, output)
        self.assertEqual((info.width, info.height), (320, 240))
        self.assertAlmostEqual(info.duration, 2, delta=0.2)
        self.assertTrue(info.audio)
        first = np.asarray(preview_frame(self.ffmpeg, output, 0.3))
        last = np.asarray(preview_frame(self.ffmpeg, output, 1.5))
        self.assertGreater(first[:, :, 2].mean(), first[:, :, 0].mean() + 100)
        self.assertGreater(last[:, :, 0].mean(), last[:, :, 2].mean() + 100)
        levels = []
        for position in (0.3, 1.4):
            code, data, error = run_ffmpeg(self.ffmpeg, ['-v', 'error', '-ss', str(position),
                '-i', str(output), '-t', '0.2', '-map', '0:a:0', '-f', 's16le', '-ac', '1', 'pipe:1'])
            self.assertEqual(code, 0, error)
            levels.append(np.abs(np.frombuffer(data, dtype='<i2').astype(float)).mean())
        self.assertLess(levels[0], 10)  # formerly silent blue clip stays silent
        self.assertGreater(levels[1], 500)  # original red clip's tone survives

    def test_refuse_overwriting_source_or_existing_output(self):
        for output in (self.red, self.root / 'existing.mp4'):
            if output != self.red:
                output.write_bytes(b'existing file')
            before = output.read_bytes()
            with self.assertRaises(ValueError):
                export_video(self.ffmpeg, [Clip(str(self.red), 0, 1)], output, (160, 120), 10)
            self.assertEqual(output.read_bytes(), before)

    def test_invalid_ranges_produce_no_output(self):
        output = self.root / 'bad.mp4'
        for start, end in ((1, 0.5), (-1, 1), (0, 3), (float('nan'), 1)):
            with self.assertRaises(ValueError):
                export_video(self.ffmpeg, [Clip(str(self.red), start, end)], output, (160, 120), 10)
        self.assertFalse(output.exists())

    def test_cancel_during_export_removes_temporary_files(self):
        cancel = threading.Event()
        output = self.root / 'cancelled.mp4'
        with self.assertRaises(EditCancelled):
            export_video(self.ffmpeg, [Clip(str(self.red), 0, 1)], output, (160, 120), 10,
                         cancel, lambda text: cancel.set())
        self.assertFalse(output.exists())
        self.assertFalse(list(self.root.glob('SmartScreenEdit_*')))

    def test_failed_encoder_preserves_sources_and_cleans_up(self):
        import video_editing
        original = video_editing.run_ffmpeg
        def fail_export(executable, args, cancel=None):
            if '-c:v' in args:
                return 1, b'', 'simulated encoder failure'
            return original(executable, args, cancel)
        with patch.object(video_editing, 'run_ffmpeg', side_effect=fail_export):
            with self.assertRaisesRegex(RuntimeError, 'encoder failure'):
                export_video(self.ffmpeg, [Clip(str(self.red), 0, 1)], self.root/'bad.mp4', (160, 120), 10)
        self.assertFalse((self.root/'bad.mp4').exists())
        self.assertFalse(list(self.root.glob('SmartScreenEdit_*')))

    def test_cancel_terminates_running_ffmpeg(self):
        cancel = threading.Event()
        timer = threading.Timer(0.3, cancel.set)
        timer.start()
        try:
            with self.assertRaises(EditCancelled):
                run_ffmpeg(self.ffmpeg, ['-v', 'error', '-re', '-f', 'lavfi',
                           '-i', 'color=s=160x120:r=10', '-f', 'null', '-'], cancel)
        finally:
            timer.cancel()
            timer.join()

    def test_file_created_during_export_is_never_overwritten(self):
        output = self.root / 'new.mp4'
        def concurrent_file(text):
            if text.startswith('Joining'):
                output.write_bytes(b'another application created this')
        with self.assertRaises(FileExistsError):
            export_video(self.ffmpeg, [Clip(str(self.red), 0, 1)], output,
                         (160, 120), 10, progress=concurrent_file)
        self.assertEqual(output.read_bytes(), b'another application created this')
        self.assertFalse(list(self.root.glob('SmartScreenEdit_*')))


if __name__ == '__main__':
    unittest.main()
