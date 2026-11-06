"""Actual Tk smoke test; run with a display (DISPLAY on Linux)."""
import os
from pathlib import Path
import tempfile
import time
import tkinter as tk
import unittest
from unittest.mock import patch

from SmartScreen_Capture_V1_0 import ffmpeg_executable
from video_editing import run_ffmpeg, probe_video
from video_editor import VideoEditor


@unittest.skipUnless(os.name == 'nt' or os.environ.get('DISPLAY'), 'Requires a graphical display')
class EditorWindowTests(unittest.TestCase):
    def test_load_preview_remove_five_seconds_reorder_export(self):
        executable = ffmpeg_executable()
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            source = directory / 'original.mp4'
            code, _, error = run_ffmpeg(executable, ['-v', 'error', '-f', 'lavfi', '-i',
                'color=c=red:s=160x120:r=10:d=7', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(source)])
            self.assertEqual(code, 0, error)
            original = source.read_bytes()
            root = tk.Tk()
            errors = []
            root.report_callback_exception = lambda *args: errors.append(args)
            try:
                editor = VideoEditor(root, executable)
                def settle():
                    deadline = time.monotonic() + 15
                    while time.monotonic() < deadline:
                        root.update()
                        if not editor.busy:
                            root.update()
                            if not editor.busy:
                                return
                        time.sleep(0.01)
                    self.fail('Editor operation did not finish: ' + editor.status.get())
                with patch('video_editor.filedialog.askopenfilenames', return_value=(str(source), str(source))):
                    editor.add()
                settle()
                self.assertEqual(len(editor.clips), 2)
                self.assertIsNotNone(editor.preview.image)
                editor.remove_tail()
                settle()
                self.assertAlmostEqual(editor.clips[0].end, 2, delta=0.02)
                editor.move(1)
                settle()
                self.assertEqual(editor.clips[1].end, 2)
                editor.remove()
                settle()
                self.assertEqual(len(editor.clips), 1)
                # Export must apply typed fields even without Apply range.
                editor.start.set('1'); editor.end.set('2')
                output = directory / 'edited.mp4'
                with patch('video_editor.filedialog.asksaveasfilename', return_value=str(output)), patch('video_editor.messagebox.showinfo'):
                    editor.export()
                    settle()
                self.assertTrue(output.is_file(), editor.status.get())
                self.assertAlmostEqual(probe_video(executable, output).duration, 1, delta=0.15)
                self.assertEqual(source.read_bytes(), original)
                self.assertFalse(errors, errors)
                self.assertGreater(editor.window.winfo_height(), 600)
                editor.window.geometry('900x680')
                root.update()
                status = editor.window.winfo_children()[0].winfo_children()[-1]
                self.assertGreater(status.winfo_height(), 0)
                self.assertLessEqual(status.winfo_rooty() + status.winfo_height(),
                                     editor.window.winfo_rooty() + editor.window.winfo_height())
                editor.close()
                deadline = time.monotonic() + 2
                while editor.window.winfo_exists() and time.monotonic() < deadline:
                    root.update(); time.sleep(0.01)
                self.assertFalse(editor.window.winfo_exists())
            finally:
                root.destroy()


if __name__ == '__main__':
    unittest.main()
