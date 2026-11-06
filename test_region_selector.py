"""Exercise real selector callbacks with a simulated Windows window manager.

No desktop is needed. Native Windows WM/DPI behavior still needs a packaged test.
"""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from contextlib import ExitStack

import SmartScreen_Capture_V1_0 as app


class Root:
    def __init__(self, state):
        self.current = state
        self.jobs = {}
        self.restores = 0
    def state(self, value=None):
        if value is not None:
            self.current = value
        return self.current
    def withdraw(self):
        self.current = 'withdrawn'
    def deiconify(self):
        self.current = 'normal'
        self.restores += 1
    def after(self, delay, callback):
        key = str(len(self.jobs))
        self.jobs[key] = callback
        return key
    def after_cancel(self, key):
        self.jobs.pop(key, None)
    def lift(self):
        pass
    def focus_set(self):
        pass


class SelectorTests(unittest.TestCase):
    def setUp(self):
        self.obj = app.ScreenshotApp.__new__(app.ScreenshotApp)
        self.obj.root = Root('zoomed')
        self.obj._recording = False
        self.obj._closing = False
        self.obj._screenshot_running = False
        self.obj._manual_taskbar_hide = True  # stale manual-hide flag must not strand UI
        self.obj._minimize_pending = True
        self.obj._taskbar_minimize_job = None
        self.obj._video_countdown_job = None
        self.obj.record_area_mode_var = SimpleNamespace(get=lambda: 'Custom Region')
        self.obj._record_area_bounds = lambda: (-1920, 0, 1920, 1080)
        self.obj._capture_region_pixels = Mock()
        self.obj._set_status = Mock()
        self.obj._record_area_changed = Mock()
        self.obj.save_config = Mock()
        self.obj.record_region = (0, 0, 50, 50)
        self.canvas = Mock()
        self.overlay = Mock()
        self.canvas_handlers, self.overlay_handlers, self.protocols = {}, {}, {}
        self.canvas.bind.side_effect = lambda key, fn: self.canvas_handlers.update({key: fn})
        self.overlay.bind.side_effect = lambda key, fn: self.overlay_handlers.update({key: fn})
        self.overlay.protocol.side_effect = lambda key, fn: self.protocols.update({key: fn})
        stack = self.enterContext(ExitStack())
        stack.enter_context(patch.object(app.tk, 'Toplevel', return_value=self.overlay))
        stack.enter_context(patch.object(app.tk, 'Canvas', return_value=self.canvas))
        stack.enter_context(patch.object(app.ImageTk, 'PhotoImage'))

    def open_selector(self):
        self.obj.select_record_area()
        self.assertEqual(self.obj.root.current, 'withdrawn')
        list(self.obj.root.jobs.values())[-1]()

    def drag(self):
        self.canvas_handlers['<ButtonPress-1>'](SimpleNamespace(x=100, y=100))
        self.canvas_handlers['<B1-Motion>'](SimpleNamespace(x=300, y=250))
        self.canvas_handlers['<ButtonRelease-1>'](SimpleNamespace(x=300, y=250))

    def test_right_click_restores_maximized_and_saves_absolute_region(self):
        self.open_selector()
        self.drag()
        self.assertEqual(self.canvas_handlers['<ButtonRelease-3>'](None), 'break')
        self.assertEqual(self.obj.root.current, 'zoomed')
        self.assertEqual(self.obj.record_region, (-1820, 100, 200, 150))
        self.obj.save_config.assert_called_once()
        self.overlay.destroy.assert_called_once()

    def test_enter_is_idempotent_even_if_event_bubbles(self):
        self.open_selector()
        self.drag()
        self.canvas_handlers['<Return>'](None)
        self.overlay_handlers['<Return>'](None)
        self.obj.save_config.assert_called_once()
        self.assertEqual(self.obj.root.restores, 1)

    def test_escape_restores_normal_and_preserves_previous_region(self):
        self.obj.root.current = 'normal'
        self.open_selector()
        self.drag()
        self.canvas_handlers['<Escape>'](None)
        self.assertEqual(self.obj.root.current, 'normal')
        self.assertEqual(self.obj.record_region, (0, 0, 50, 50))
        self.obj.save_config.assert_not_called()

    def test_window_close_cancels_and_restores(self):
        self.open_selector()
        self.protocols['WM_DELETE_WINDOW']()
        self.assertEqual(self.obj.root.current, 'zoomed')
        self.obj.save_config.assert_not_called()

    def test_right_click_without_rectangle_restores_without_saving(self):
        self.open_selector()
        self.canvas_handlers['<ButtonRelease-3>'](None)
        self.assertEqual(self.obj.root.current, 'zoomed')
        self.obj.save_config.assert_not_called()

    def test_overlay_error_destroys_partial_window_and_restores(self):
        self.canvas.pack.side_effect = app.tk.TclError('simulated canvas failure')
        with self.assertLogs(level='ERROR'):
            self.open_selector()
        self.overlay.destroy.assert_called_once()
        self.assertEqual(self.obj.root.current, 'zoomed')

    def test_capture_error_restores_even_before_overlay_creation(self):
        self.obj._capture_region_pixels.side_effect = RuntimeError('capture failed')
        with self.assertLogs(level='ERROR'):
            self.open_selector()
        self.assertEqual(self.obj.root.current, 'zoomed')

    def test_second_selection_does_not_overwrite_restore_state(self):
        self.open_selector()
        self.obj.select_record_area()
        self.canvas_handlers['<Escape>'](None)
        self.assertEqual(self.obj.root.current, 'zoomed')

    def test_pending_screenshot_blocks_selection(self):
        self.obj._screenshot_running = True
        self.obj.select_record_area()
        self.assertEqual(self.obj.root.current, 'zoomed')
        self.assertFalse(self.obj.root.jobs)


if __name__ == '__main__':
    unittest.main()
