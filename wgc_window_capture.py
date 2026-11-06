"""Independent per-HWND Windows Graphics Capture for SmartScreen.

Requires Windows 10 1903+ with a supported graphics environment, Windows x64,
and windows-capture 2.0.1. Never silently substitutes a desktop crop.
"""
import ctypes
import os
import struct
import threading
import time

from PIL import Image


def validate_window_capture(hwnd):
    if os.name != "nt":
        raise RuntimeError("Selected Window independent capture requires Windows 10/11")
    if struct.calcsize("P") != 8:
        raise RuntimeError("Independent Selected Window recording is unavailable in x86. Use the x64 SmartScreen build.")
    if not hwnd or not ctypes.windll.user32.IsWindow(int(hwnd)):
        raise RuntimeError("Selected HMI window is no longer available. Select it again.")
    if ctypes.windll.user32.IsIconic(int(hwnd)):
        raise RuntimeError("Selected HMI is minimized. Restore it before recording.")
    try:
        from windows_capture import WindowsCapture
    except (ImportError, OSError) as exc:
        raise RuntimeError("Windows Graphics Capture backend unavailable. Install windows-capture on x64 and rebuild SmartScreen.") from exc
    return WindowsCapture


class WindowCaptureSource:
    """Thread-safe latest-frame snapshot with bounded memory and stopped-state detection."""
    def __init__(self, hwnd):
        self.hwnd = int(hwnd)
        self._cls = validate_window_capture(hwnd)
        self._latest = None
        self._last_frame_time = None
        self._error = None
        self._closed = False
        self._lock = threading.Lock()
        self._frame_ready = threading.Event()
        self._capture = None
        self._control = None

    def start(self):
        capture = self._cls(window_hwnd=self.hwnd, cursor_capture=False,
                            draw_border=False, monitor_index=None,
                            minimum_update_interval=100)

        @capture.event
        def on_frame_arrived(frame, capture_control):
            try:
                # frame_buffer is a BGRA NumPy array; copy before callback returns,
                # since the original storage is owned by the capture backend.
                arr = frame.frame_buffer
                img = Image.fromarray(arr[:, :, [2, 1, 0]].copy(), mode="RGB")
                with self._lock:
                    self._latest = img
                    self._last_frame_time = time.monotonic()
                self._frame_ready.set()
            except Exception as exc:
                with self._lock:
                    self._error = f"WGC frame conversion failed: {exc}"
                self._frame_ready.set()
                capture_control.stop()

        @capture.event
        def on_closed():
            with self._lock:
                if not self._closed:
                    self._error = "Selected HMI window capture session closed"
            self._frame_ready.set()

        try:
            self._control = capture.start_free_threaded()
        except Exception as exc:
            raise RuntimeError(f"Unable to start Windows Graphics Capture: {exc}") from exc
        self._capture = capture

    def get_frame(self, timeout=2):
        if ctypes.windll.user32.IsIconic(self.hwnd):
            raise RuntimeError("Selected HMI was minimized; recording cannot continue")
        if not ctypes.windll.user32.IsWindow(self.hwnd):
            raise RuntimeError("Selected HMI window has closed")
        with self._lock:
            if self._error:
                raise RuntimeError(self._error)
            if self._latest is not None:
                return self._latest.copy()
        if not self._frame_ready.wait(timeout):
            raise RuntimeError("No window-capture frame received. Check graphics support or HMI rendering.")
        with self._lock:
            if self._error:
                raise RuntimeError(self._error)
            if self._latest is None:
                raise RuntimeError("Window capture returned no image")
            return self._latest.copy()

    def close(self):
        with self._lock:
            self._closed = True
        if self._control is not None:
            self._control.stop()
            # Do not block GUI shutdown indefinitely on a faulty graphics driver.
        self._capture = None
