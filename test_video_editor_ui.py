"""Actual Tk smoke test; run with a display (DISPLAY on Linux)."""
import os
from pathlib import Path
import tempfile
import subprocess
import shutil
import time
import tkinter as tk
import unittest
from unittest.mock import patch

from SmartScreen_Capture_V1_0 import ffmpeg_executable
from video_editing import run_ffmpeg, probe_video
from video_editor import VideoEditor


@unittest.skipUnless(os.name == 'nt' or os.environ.get('DISPLAY'), 'Requires a graphical display')
class EditorWindowTests(unittest.TestCase):
    def tearDown(self):
        # Collect destroyed Tk interpreters on the GUI thread, never in a later
        # decoder worker during a multi-test process.
        import gc
        gc.collect()

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
                deadline = time.monotonic() + 5
                while getattr(editor.preview, 'image', None) is None and time.monotonic() < deadline:
                    root.update(); time.sleep(0.01)
                self.assertIsNotNone(getattr(editor.preview, 'image', None))
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
                if 'editor' in locals():
                    editor.player.close()
                    editor.player.thread.join(timeout=5)
                root.destroy()

    def test_drop_play_timeline_focus_and_resizing(self):
        from types import SimpleNamespace
        executable = ffmpeg_executable()
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / 'clip {one} ü.mp4'
            second = Path(td) / 'second video.mp4'
            code, _, error = run_ffmpeg(executable, ['-v', 'error', '-f', 'lavfi', '-i',
                'testsrc2=s=160x120:r=10:d=4', '-f', 'lavfi', '-i', 'sine=duration=4',
                '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-t', '4', str(source)])
            self.assertEqual(code, 0, error)
            second.write_bytes(source.read_bytes())
            root = tk.Tk(); errors = []
            root.report_callback_exception = lambda *args: errors.append(args)
            editor = VideoEditor(root, executable)
            other = tk.Toplevel(root)
            try:
                def wait(predicate, seconds=8):
                    deadline = time.monotonic()+seconds
                    while time.monotonic()<deadline:
                        root.update()
                        if predicate():
                            return
                        time.sleep(0.01)
                    self.fail('GUI condition timed out: '+editor.status.get())
                root.update()
                self.assertFalse(editor.window.transient())
                self.assertIsNone(editor.window.grab_current())
                self.assertEqual(editor.window.resizable(), (1, 1))
                self.assertTrue(editor.window.tk.call('package', 'present', 'tkdnd'))
                data = root.tk.call('format', '%s', root.tk.call('list', str(source), str(second)))
                self.assertEqual(editor.drop_files(SimpleNamespace(data=data)), 'copy')
                wait(lambda: len(editor.clips)==2 and not editor.busy)
                wait(lambda: editor._display_image is not None)
                # Drag both selection handles, using actual Tk mouse events.
                timeline = editor.timeline
                timeline.event_generate('<ButtonPress-1>', x=int(timeline.x(0)), y=20)
                timeline.event_generate('<B1-Motion>', x=int(timeline.x(0.5)), y=20)
                timeline.event_generate('<ButtonRelease-1>', x=int(timeline.x(0.5)), y=20)
                root.update()
                self.assertAlmostEqual(editor.clips[0].start, 0.5, delta=0.11)
                timeline.event_generate('<ButtonPress-1>', x=int(timeline.x(4)), y=20)
                timeline.event_generate('<B1-Motion>', x=int(timeline.x(2.5)), y=20)
                timeline.event_generate('<ButtonRelease-1>', x=int(timeline.x(2.5)), y=20)
                root.update()
                self.assertAlmostEqual(editor.clips[0].end, 2.5, delta=0.11)
                if os.name == 'nt':
                    editor.toggle_maximize()
                    wait(lambda: editor.window.state() == 'zoomed' if os.name == 'nt'
                         else bool(editor.window.attributes('-zoomed')))
                    editor.toggle_maximize()
                    wait(lambda: editor.window.state() == 'normal' if os.name == 'nt'
                         else not bool(editor.window.attributes('-zoomed')))
                # Scrub inside the selection; Play must resume at that position.
                editor.scrub(1)
                wait(lambda: editor._seek_job is None)
                editor.toggle_play()
                wait(lambda: editor.position.get()>1.2)
                self.assertTrue(editor.playing)
                # Repeat actual focus changes and UI layout events while decoding.
                for _ in range(3):
                    other.lift(); other.focus_force(); root.update()
                    editor.window.lift(); editor.window.focus_force(); root.update()
                if os.name != 'nt' and shutil.which('xmessage'):
                    external = subprocess.Popen(['xmessage', '-timeout', '2', 'SmartScreen focus test'],
                                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    try:
                        for _ in range(8):
                            root.update(); time.sleep(0.02)
                        editor.window.lift(); editor.window.focus_force(); root.update()
                    finally:
                        external.terminate(); external.wait(timeout=3)
                editor.window.geometry('1200x900'); root.update()
                self.assertFalse(editor.busy)
                self.assertIsNone(editor.window.grab_current())
                editor.toggle_play()
                self.assertFalse(editor.playing)
                before = editor.position.get()
                editor.step_frame(1)
                self.assertAlmostEqual(editor.position.get(), before+0.1, delta=0.01)
                # Moving handles and scrubbing must remain possible after playback.
                editor.start.set('0'); editor.end.set('0.4')
                editor.apply_range(preview=False)
                editor.toggle_play()
                # Do not service Tk temporarily: there must be no frame backlog,
                # and the transport must recover its ended state on return.
                time.sleep(0.8)
                self.assertLessEqual(editor.player.frames.qsize(), 1)
                wait(lambda: not editor.playing)
                self.assertFalse(errors, errors)
                editor.close()
                wait(lambda: not editor.window.winfo_exists())
            finally:
                editor.player.close(); editor.player.thread.join(timeout=5)
                root.destroy()


if __name__ == '__main__':
    unittest.main()
