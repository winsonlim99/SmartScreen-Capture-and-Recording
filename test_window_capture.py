"""WGC wrapper tests using an event-driven fake backend; native WGC needs Windows."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np
import wgc_window_capture as wgc


class Backend:
    def __init__(self, **kwargs):
        self.handlers = {}
        self.control = Mock()
    def event(self, handler):
        self.handlers[handler.__name__] = handler
        return handler
    def start_free_threaded(self):
        return self.control


class WindowCaptureTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.object(wgc, 'validate_window_capture', return_value=Backend))
        self.user32 = SimpleNamespace(IsWindow=lambda h: True, IsIconic=lambda h: False)
        self.enterContext(patch.object(wgc.ctypes, 'windll', SimpleNamespace(user32=self.user32), create=True))
        self.source = wgc.WindowCaptureSource(42)
        self.source.start()
        self.addCleanup(self.source.close)

    def test_copies_bgra_pixels_before_callback_returns(self):
        pixels = np.array([[[10, 20, 30, 255]]], dtype=np.uint8)
        self.source._capture.handlers['on_frame_arrived'](SimpleNamespace(frame_buffer=pixels), Mock())
        pixels[:] = 0
        image = self.source.get_frame()
        self.assertEqual(image.getpixel((0, 0)), (30, 20, 10))
        image.putpixel((0, 0), (0, 0, 0))
        self.assertEqual(self.source.get_frame().getpixel((0, 0)), (30, 20, 10))

    def test_closed_session_reports_error(self):
        self.source._capture.handlers['on_closed']()
        with self.assertRaisesRegex(RuntimeError, 'session closed'):
            self.source.get_frame()

    def test_no_first_frame_times_out(self):
        with self.assertRaisesRegex(RuntimeError, 'No window-capture frame'):
            self.source.get_frame(timeout=0)

    def test_minimized_window_is_rejected(self):
        self.user32.IsIconic = lambda h: True
        with self.assertRaisesRegex(RuntimeError, 'minimized'):
            self.source.get_frame(timeout=0)

    def test_destroyed_window_is_rejected(self):
        self.user32.IsWindow = lambda h: False
        with self.assertRaisesRegex(RuntimeError, 'has closed'):
            self.source.get_frame(timeout=0)

    def test_bad_frame_stops_capture_and_reports_error(self):
        control = Mock()
        self.source._capture.handlers['on_frame_arrived'](SimpleNamespace(frame_buffer=None), control)
        control.stop.assert_called_once()
        with self.assertRaisesRegex(RuntimeError, 'conversion failed'):
            self.source.get_frame(timeout=0)


if __name__ == '__main__':
    unittest.main()
