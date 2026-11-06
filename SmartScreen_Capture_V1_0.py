#!/usr/bin/env python3
"""
screenshot_app.py

SmartScreen Capture & Recording V1.0 — compatibility, reliability and optional recording preview.

Features:
- All previous features retained.
- Optional dependency on `mss` (recommended). If available, mss is used for per-monitor captures.
- New UI: "Select monitor" checkbox + monitor combobox to choose which monitor to capture (or All).
- Monitor enumeration uses mss when available; fallback to a Windows ctypes enumeration when mss is missing.
- DPI awareness enabled on Windows to reduce scaling / black-capture issues.
- Config persists monitor selection and the Select-monitor checkbox.
- Attempts to capture the selected monitor; falls back gracefully to combined virtual screen capture if needed.
- New: Basic screen recording support (MP4) with selectable FPS and resolution (Native / 1080p / 1440p).
  - Independently detects imageio/FFmpeg and OpenCV; tries H.264 then OpenCV MP4 codecs.
  - Recording is run on a background thread; Start/Stop buttons added.
  - Recording settings (fps, resolution) are persisted to config.

Dependencies:
    pip install pillow keyboard mss
    Optional (recommended for recording): pip install opencv-python
    Recommended recording: pip install imageio imageio-ffmpeg numpy
    Alternative recording: pip install opencv-python numpy

Note: For global keyboard hooks and some capture scenarios on Windows you may need to run as Administrator.
"""

import os
import sys
import json
import time
import threading
import queue
import logging
import re
import tempfile
import shutil
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from datetime import datetime
from pathlib import Path
import math

# Make process DPI aware on Windows to help with correct monitor coordinates / scaling.
if os.name == "nt":
    try:
        import ctypes
        # Prefer SetProcessDpiAwarenessContext (Windows 10+), then SetProcessDpiAwareness, then SetProcessDPIAware
        try:
            # PER_MONITOR_AWARE_V2 is -4 on supported Windows versions
            ctypes.windll.user32.SetProcessDpiAwarenessContext(-4)
        except Exception:
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
            except Exception:
                try:
                    ctypes.windll.user32.SetProcessDPIAware()
                except Exception:
                    pass
    except Exception:
        pass

try:
    # Use Image and ImageTk for loading icons and fallback screen grab
    from PIL import ImageGrab, Image, ImageTk
except Exception as e:
    raise SystemExit("Pillow is required. Install with: pip install pillow") from e

try:
    import keyboard
except Exception as e:
    raise SystemExit("keyboard module is required. Install with: pip install keyboard") from e

# Try to import mss (optional but recommended for reliable per-monitor captures)
try:
    import mss
    import mss.tools
    MSS_AVAILABLE = True
except Exception:
    MSS_AVAILABLE = False

# Independent optional backend probes. Encoders are validated by actually opening them.
try:
    import numpy as np
except Exception:
    np = None
try:
    import cv2
except Exception:
    cv2 = None
try:
    import imageio
except Exception:
    imageio = None
try:
    import imageio_ffmpeg
except Exception:
    imageio_ffmpeg = None
_cv2_available = cv2 is not None and np is not None
_imageio_available = imageio is not None and np is not None


def resource_locations():
    """Development and frozen executable asset roots, in preference order."""
    roots = []
    if getattr(sys, 'frozen', False):
        roots.append(Path(sys.executable).resolve().parent)
    roots.extend((Path(__file__).resolve().parent, Path.cwd()))
    return tuple(dict.fromkeys(roots))


def find_resource(*names):
    for root in resource_locations():
        for name in names:
            candidate = root / name
            if candidate.is_file():
                return candidate
    return None


def ffmpeg_executable():
    """Locate a compatible ffmpeg executable without requiring PATH."""
    candidates = []
    try:
        base = Path(sys.executable if getattr(sys, 'frozen', False) else __file__).resolve().parent
        candidates += [base / 'ffmpeg' / 'ffmpeg.exe', base / 'ffmpeg.exe', base / 'ffmpeg']
    except Exception:
        pass
    from_path = shutil.which('ffmpeg')
    if from_path:
        candidates.append(Path(from_path))
    for item in candidates:
        if item.is_file():
            return str(item)
    if imageio_ffmpeg is not None:
        try:
            return imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            pass
    return None


class RecordingWriter:
    """Common writer adapter; imageio/FFmpeg preferred, cv2/mp4v fallback."""
    def __init__(self, path, fps, size):
        self.path, self.fps, self.size = str(path), fps, size
        self.writer, self.backend, self.errors = None, None, []
        if _imageio_available:
            try:
                # Set executable explicitly: supports bundled imageio-ffmpeg and local ffmpeg.exe.
                exe = ffmpeg_executable()
                if not exe:
                    raise RuntimeError('FFmpeg executable not found')
                os.environ['IMAGEIO_FFMPEG_EXE'] = exe
                def open_writer(target):
                    return imageio.get_writer(target, format='FFMPEG', mode='I', fps=fps,
                                              codec='libx264', macro_block_size=1,
                                              pixelformat='yuv420p')
                # Probe a separate file; real recordings must start with screen pixels.
                with tempfile.TemporaryDirectory() as probe_dir:
                    probe = open_writer(os.path.join(probe_dir, 'probe.mp4'))
                    try:
                        probe.append_data(np.zeros((size[1], size[0], 3), dtype=np.uint8))
                    finally:
                        probe.close()
                self.writer = open_writer(self.path)
                self.backend = 'FFmpeg (H.264)'
                return
            except Exception as exc:
                self.errors.append('FFmpeg/H.264: ' + str(exc))
                try:
                    if self.writer is not None:
                        self.writer.close()
                except Exception:
                    pass
                self.writer = None
                try:
                    os.remove(self.path)
                except OSError:
                    pass
        if _cv2_available:
            try:
                for codec in ('mp4v', 'avc1'):
                    writer = cv2.VideoWriter(self.path, cv2.VideoWriter_fourcc(*codec),
                                             float(fps), size)
                    if writer is not None and writer.isOpened():
                        self.writer, self.backend = writer, 'OpenCV (' + codec + ')'
                        return
                    if writer is not None:
                        writer.release()
                    self.errors.append('OpenCV ' + codec + ': encoder not available')
            except Exception as exc:
                self.errors.append('OpenCV: ' + str(exc))
        raise RuntimeError('No usable MP4 encoder. ' + '; '.join(self.errors) +
                           '. Install imageio imageio-ffmpeg or opencv-python.')

    def write(self, rgb):
        if self.backend.startswith('OpenCV'):
            self.writer.write(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
        else:
            self.writer.append_data(rgb)

    def close(self):
        if self.writer is not None:
            if self.backend.startswith('OpenCV'):
                self.writer.release()
            else:
                self.writer.close()
            self.writer = None


class RecordingTimeline:
    """Fill missed fixed-FPS slots with the last capture to preserve elapsed time."""
    def __init__(self, writer, fps):
        self.writer, self.fps = writer, fps
        self.started = None
        self.frames = 0
        self.previous = None

    def write(self, rgb, captured_at):
        if self.started is None:
            self.writer.write(rgb)
            self.started = captured_at
            self.frames = 1
            self.previous = rgb
            return 1
        target = int((captured_at - self.started) * self.fps + 1e-6) + 1
        added = 0
        while self.frames < target - 1:
            self.writer.write(self.previous)
            self.frames += 1
            added += 1
        if self.frames < target:
            self.writer.write(rgb)
            self.frames += 1
            added += 1
        self.previous = rgb
        return added


# File sizes are checked periodically while recording, and again after closing.
# MP4 muxers can buffer metadata, so segment rollover happens substantially before 1 GB.
VIDEO_FILE_MAX_BYTES = 1_000_000_000
VIDEO_ROLLOVER_BYTES = 850_000_000
MIN_FREE_DISK_BYTES = 2_000_000_000


class ScreenshotApp:
    CONFIG_DIR_NAME = "screenshot_app"  # Retain previous config location for upgrade compatibility
    CONFIG_FILE_NAME = "config.json"

    # Trigger option labels
    TRIGGER_OPTIONS = [
        "Ctrl x 2",
        "Shift x 2",
        "F key x 2",
    ]

    FK_KEYS = [f"F{i}" for i in range(1, 13)]

    ABOUT_TEXT = (
        "SmartScreen Capture & Recording — v1.0 (build 1.0.6)\n\n"
        "Fast, configurable screenshot capture tool.\n\n"
        "- Double-press triggers: Ctrl x 2 | Shift x 2 | F1–F12 x 2\n"
        "For global hotkeys to work reliably on Windows, run the program as Administrator.\n\n\n"
        "Created by Winson Lim for Siliconbox internal use only.."
    )

    # candidate icon filenames to look for (in script dir)
    ICON_FILENAMES = ["assets/ASC_Logo.ico", "assets/ASC_Logo.png", "SiliconBox.ico", "SiliconBox.png", "siliconbox.ico", "siliconbox.png"]

    def __init__(self, root):
        self.root = root
        self.root.title("SmartScreen Capture & Recording V1.0")
        # Allow resizing (maximizing) of the window
        self.root.resizable(True, True)

        # Ensure grid expansion support so maximizing behaves reasonably
        try:
            self.root.columnconfigure(0, weight=1)
            self.root.rowconfigure(0, weight=1)
        except Exception:
            pass

        # Initialize GUI dispatch before icon-loading can post status messages.
        self._gui_queue = queue.Queue()
        self._closing = False
        # Attempt to load app icon early during startup
        self._icon_photo = None  # keep reference if using PhotoImage
        self._load_app_icon()

        self.root.configure(bg="#edf2f7")
        style = ttk.Style(root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("App.TFrame", background="#edf2f7")
        style.configure("Panel.TFrame", background="#ffffff")
        style.configure("Header.TLabel", background="#edf2f7", foreground="#14233a", font=("Segoe UI", 19, "bold"))
        style.configure("Subtitle.TLabel", background="#edf2f7", foreground="#65758b", font=("Segoe UI", 11))
        style.configure("Section.TLabel", background="#ffffff", foreground="#1b314d", font=("Segoe UI", 12, "bold"))
        style.configure("Body.TLabel", background="#ffffff", foreground="#43536b", font=("Segoe UI", 11))
        style.configure("TButton", font=("Segoe UI", 10), padding=(8, 5))
        style.configure("TCheckbutton", font=("Segoe UI", 10), background="#ffffff")
        style.configure("TCombobox", padding=(5, 4))
        style.configure("TEntry", padding=(5, 4))

        self.save_as_var = tk.StringVar()
        self.save_dir_var = tk.StringVar(value=str(Path.home() / "Pictures" / "SmartScreen Captures"))
        self.trigger_var = tk.StringVar(value=self.TRIGGER_OPTIONS[0])
        self.fkey_var = tk.StringVar(value="F8")
        self.use_delay_var = tk.BooleanVar(value=True)
        self.delay_seconds_var = tk.IntVar(value=3)
        self.video_delay_seconds_var = tk.IntVar(value=3)
        self.hide_during_capture_var = tk.BooleanVar(value=True)
        self._video_countdown_job = None
        self._video_countdown_remaining = 0
        self._screenshot_running = False
        self._manual_taskbar_hide = False
        self._auto_record_minimized = False
        self._taskbar_minimize_job = None
        self._taskbar_minimize_attempts = 0
        self._minimize_pending = False
        self.use_monitor_select_var = tk.BooleanVar(value=False)
        self.monitor_list_var = tk.StringVar()
        self.scale_var = tk.StringVar(value="1.0x")
        self.rec_fps_var = tk.IntVar(value=10)
        self.rec_res_var = tk.StringVar(value="Native")
        self.show_preview_var = tk.BooleanVar(value=False)
        self.record_area_mode_var = tk.StringVar(value='Full Screen')
        self.record_region = None  # absolute desktop pixels: left, top, width, height
        self.selected_window_hwnd = None  # HWND is session-local and never persisted
        self.selected_window_title = ''
        self.record_area_summary = tk.StringVar(value='Full screen')
        self.record_stats_var = tk.StringVar(value="Standby · 00:00:00 · 0 frames")
        self.record_segment_var = tk.StringVar(value="1 GB/file · No active recording")
        self._record_phase = 'Ready'
        self._record_part = 0
        self._record_segment_bytes = 0
        self._record_path = ''
        self._record_error = None
        self._record_success = False
        self._normal_icon = None
        self._rec_icon = None
        self._record_stop_event = threading.Event()
        self.status_var = tk.StringVar(value="Ready to capture")
        self.last_file_var = tk.StringVar(value="No capture yet")
        self._latest_capture = None
        self._display_mode = "screenshot"
        self._preview_image = None
        self._preview_frame = None
        self._preview_lock = threading.Lock()
        self._preview_enabled = threading.Event()
        self._record_start_monotonic = None
        self._record_frames = 0
        self._monitors_cache = []

        main = ttk.Frame(root, style="App.TFrame", padding=10)
        main.grid(row=0, column=0, sticky="nsew")
        main.columnconfigure(0, weight=0, minsize=550)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(1, weight=1)

        header = ttk.Frame(main, style="App.TFrame")
        header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        if self._header_logo is not None:
            ttk.Label(header, image=self._header_logo, background="#edf2f7").pack(side="left", padx=(0, 12))
        headings = ttk.Frame(header, style="App.TFrame")
        headings.pack(side="left", fill="x", expand=True)
        ttk.Label(headings, text="SmartScreen Capture & Recording", style="Header.TLabel").pack(anchor="w")
        ttk.Label(headings, text="V1.0  ·  Engineering capture workspace", style="Subtitle.TLabel").pack(anchor="w")
        ttk.Button(header, text="Help", command=self.show_about).pack(side="right")

        # 550-pixel controls pane, readable at 1024x768 with remaining preview space.
        left = ttk.Frame(main, style="Panel.TFrame", padding=(14, 12))
        left.grid(row=1, column=0, sticky="nsew", padx=(0, 10))
        left.columnconfigure(0, weight=1)
        r = 0
        ttk.Label(left, text="SAVE & DISPLAY", style="Section.TLabel").grid(row=r, column=0, sticky="w", pady=(0, 5)); r += 1
        row = ttk.Frame(left, style="Panel.TFrame")
        row.grid(row=r, column=0, sticky="ew", pady=(0, 5)); r += 1
        row.columnconfigure(1, weight=1)
        ttk.Label(row, text="Save As", style="Body.TLabel", width=11).grid(row=0,column=0,sticky="w")
        ttk.Entry(row, textvariable=self.save_as_var).grid(row=0,column=1,sticky="ew")
        row=ttk.Frame(left,style="Panel.TFrame"); row.grid(row=r,column=0,sticky="ew",pady=(0,5));r+=1
        row.columnconfigure(1,weight=1)
        ttk.Label(row,text="Save Folder",style="Body.TLabel",width=11).grid(row=0,column=0,sticky="w")
        self.save_dir_entry=ttk.Entry(row,textvariable=self.save_dir_var)
        self.save_dir_entry.grid(row=0,column=1,sticky="ew")
        ttk.Button(row,text="Browse",command=self.browse_folder).grid(row=0,column=2,padx=(5,0))
        self.save_folder_path_label=ttk.Label(left,textvariable=self.save_dir_var,
                                              style="Body.TLabel",wraplength=515)
        self.save_folder_path_label.grid(row=r,column=0,sticky="w",pady=(0,5));r+=1
        row=ttk.Frame(left,style="Panel.TFrame");row.grid(row=r,column=0,sticky="ew",pady=(0,5));r+=1
        ttk.Label(row,text="Monitor",style="Body.TLabel",width=11).pack(side="left")
        self.monitor_select_check=ttk.Checkbutton(row,text="Select",variable=self.use_monitor_select_var,
                                                   command=self._on_monitor_toggle)
        self.monitor_select_check.pack(side="left",padx=(0,5))
        self.monitor_combo=ttk.Combobox(row,textvariable=self.monitor_list_var,state="disabled",width=26)
        self.monitor_combo.pack(side="left",fill="x",expand=True)
        self._populate_monitor_list()
        ttk.Separator(left).grid(row=r,column=0,sticky="ew",pady=5);r+=1
        section=ttk.Frame(left,style="Panel.TFrame")
        section.grid(row=r,column=0,sticky="ew",pady=(0,4));r+=1
        ttk.Label(section,text="SCREENSHOT",style="Section.TLabel").pack(side="left")
        self.hotkey_hint=ttk.Label(section,text="Double Ctrl",style="Body.TLabel")
        self.hotkey_hint.pack(side="right")
        # Two generous rows make every control legible without horizontal crowding.
        row=ttk.Frame(left,style="Panel.TFrame");row.grid(row=r,column=0,sticky="ew",pady=(0,7));r+=1
        ttk.Label(row,text="Trigger",style="Body.TLabel").pack(side="left",padx=(0,9))
        self.trigger_combo=ttk.Combobox(row,textvariable=self.trigger_var,values=self.TRIGGER_OPTIONS,
                                         state="readonly",width=15)
        self.trigger_combo.pack(side="left",padx=(0,12))
        self.trigger_combo.bind("<<ComboboxSelected>>",lambda e:self._on_trigger_change())
        ttk.Label(row,text="F-Key",style="Body.TLabel").pack(side="left",padx=(0,7))
        self.fkey_combo=ttk.Combobox(row,textvariable=self.fkey_var,values=self.FK_KEYS,state="disabled",width=6)
        self.fkey_combo.pack(side="left")
        self.fkey_combo.bind("<<ComboboxSelected>>",lambda e:self._on_trigger_change())
        row=ttk.Frame(left,style="Panel.TFrame");row.grid(row=r,column=0,sticky="ew",pady=(0,9));r+=1
        self.delay_check=ttk.Checkbutton(row,text="Delay",variable=self.use_delay_var,
                                          command=self._on_delay_toggle)
        self.delay_check.pack(side="left",padx=(0,7))
        self.main_delay_spin=tk.Spinbox(row,from_=0,to=60,textvariable=self.delay_seconds_var,
                                        width=5,justify="center",font=("Segoe UI",11))
        self.main_delay_spin.pack(side="left",padx=(0,6))
        ttk.Label(row,text="sec",style="Body.TLabel").pack(side="left",padx=(0,30))
        ttk.Label(row,text="Image Scale",style="Body.TLabel").pack(side="left",padx=(0,9))
        self.delay_spin=self.main_delay_spin
        self.scale_combo=ttk.Combobox(row,textvariable=self.scale_var,
                                       values=["1.0x","1.5x","2.0x","3.0x"],state="readonly",width=7)
        self.scale_combo.pack(side="left")
        self.capture_btn=tk.Button(left,text="Capture Screenshot",font=("Segoe UI",12,"bold"),
                                    bg="#246be8",fg="white",relief="flat",pady=10,
                                    activebackground="#1852b9",activeforeground="white",command=self.capture_now)
        self.capture_btn.grid(row=r,column=0,sticky="ew",pady=(0,7));r+=1
        ttk.Separator(left).grid(row=r,column=0,sticky="ew",pady=5);r+=1
        ttk.Label(left,text="VIDEO RECORDING",style="Section.TLabel").grid(row=r,column=0,sticky="w",pady=(0,4));r+=1
        # Recording mode and associated selection actions in two readable rows.
        region_row=ttk.Frame(left,style="Panel.TFrame")
        region_row.grid(row=r,column=0,sticky="ew",pady=(0,3));r+=1
        ttk.Label(region_row,text="Area",style="Body.TLabel").pack(side="left",padx=(0,8))
        self.area_mode_combo=ttk.Combobox(region_row,
                values=["Full Screen","Custom Region","Selected Window"],
                state="readonly",width=19,textvariable=self.record_area_mode_var)
        self.area_mode_combo.pack(side="left")
        self.area_mode_combo.bind("<<ComboboxSelected>>",self._record_area_changed)
        self.selection_buttons=ttk.Frame(left,style="Panel.TFrame")
        self.selection_buttons.grid(row=r,column=0,sticky="ew",pady=(0,3));r+=1
        self.select_region_btn=ttk.Button(self.selection_buttons,text="Select Area",command=self.select_record_area)
        self.select_region_btn.pack(side="left",padx=(0,7))
        self.show_region_btn=ttk.Button(self.selection_buttons,text="Show Area",command=self.show_record_area)
        self.show_region_btn.pack(side="left")
        ttk.Label(left,textvariable=self.record_area_summary,style="Body.TLabel",wraplength=515).grid(
            row=r,column=0,sticky="w",pady=(0,5));r+=1
        row=ttk.Frame(left,style="Panel.TFrame");row.grid(row=r,column=0,sticky="ew",pady=(0,5));r+=1
        ttk.Label(row,text="Resolution",style="Body.TLabel").pack(side="left",padx=(0,5))
        self.rec_res_combo=ttk.Combobox(row,textvariable=self.rec_res_var,
                                         values=["Native","1080p","1440p"],state="readonly",width=9)
        self.rec_res_combo.pack(side="left",padx=(0,10))
        ttk.Label(row,text="FPS",style="Body.TLabel").pack(side="left",padx=(0,4))
        self.rec_fps_spin=tk.Spinbox(row,from_=5,to=60,textvariable=self.rec_fps_var,width=5,justify="center",font=("Segoe UI",11))
        self.rec_fps_spin.pack(side="left",padx=(0,10))
        ttk.Label(row,text="Start delay",style="Body.TLabel").pack(side="left",padx=(0,4))
        self.video_delay_spin=tk.Spinbox(row,from_=0,to=60,textvariable=self.video_delay_seconds_var,
                                         width=5,justify="center",font=("Segoe UI",11))
        self.video_delay_spin.pack(side="left")
        self.record_quality_var=tk.StringVar(value="Native · 10 FPS")
        self.rec_res_var.trace_add("write",lambda *_:self._update_quality_label())
        self.rec_fps_var.trace_add("write",lambda *_:self._update_quality_label())
        row=ttk.Frame(left,style="Panel.TFrame");row.grid(row=r,column=0,sticky="ew",pady=(0,4));r+=1
        row.columnconfigure(0,weight=1);row.columnconfigure(1,weight=1)
        self.start_rec_btn=tk.Button(row,text="Start Recording",bg="#16835d",fg="white",
                                     font=("Segoe UI",12,"bold"),relief="flat",pady=10,
                                     command=self.start_recording)
        self.start_rec_btn.grid(row=0,column=0,sticky="ew",padx=(0,4))
        self.stop_rec_btn=tk.Button(row,text="Stop Recording",bg="#b4343b",fg="white",
                                    font=("Segoe UI",12,"bold"),relief="flat",pady=10,
                                    state="disabled",command=self.stop_recording)
        self.stop_rec_btn.grid(row=0,column=1,sticky="ew")
        self.rec_indicator = tk.Label(left, text='●  READY', font=('Segoe UI', 12, 'bold'),
                                      bg='#ffffff', fg='#58677a', anchor='w')
        self.rec_indicator.grid(row=r, column=0, sticky='ew', pady=(2, 2)); r += 1
        ttk.Label(left,textvariable=self.record_stats_var,style="Body.TLabel").grid(
            row=r,column=0,sticky="w",pady=(0,2));r+=1
        ttk.Label(left,textvariable=self.record_segment_var,style="Body.TLabel",wraplength=520).grid(
            row=r,column=0,sticky="w",pady=(0,5));r+=1
        row=ttk.Frame(left,style="Panel.TFrame");row.grid(row=r,column=0,sticky="ew",pady=(0,3));r+=1
        ttk.Button(row,text="Check Recorder",command=self.check_recording).pack(side="left",padx=(0,10))
        ttk.Button(row,text="Save Config",command=self.save_config).pack(side="left",padx=(0,10))
        ttk.Checkbutton(left,text="Minimize before capture / recording",
                        variable=self.hide_during_capture_var).grid(row=r,column=0,sticky="w",pady=(0,2));r+=1

        right = ttk.Frame(main, style="Panel.TFrame", padding=12)
        right.grid(row=1, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)
        preview_header = ttk.Frame(right, style="Panel.TFrame")
        preview_header.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ttk.Label(preview_header, text="CAPTURE PREVIEW", style="Section.TLabel").pack(side="left")
        ttk.Checkbutton(preview_header, text="Live video preview", variable=self.show_preview_var,
                        command=self._toggle_preview).pack(side="right")
        self.preview_holder = tk.Frame(right, background="#172335", highlightthickness=1,
                                       highlightbackground="#d9e1eb")
        self.preview_holder.grid(row=1, column=0, sticky="nsew")
        self.preview_holder.grid_propagate(False)
        self.preview_label = tk.Label(self.preview_holder, bg="#172335", fg="#a7b8cd",
                                      text="Your latest screenshot will appear here\n\nCapture a screen to begin",
                                      font=("Segoe UI", 11), compound="center")
        self.preview_label.pack(fill="both", expand=True, padx=4, pady=4)
        self.preview_holder.bind("<Configure>", self._preview_resized)
        preview_foot = ttk.Frame(right, style="Panel.TFrame")
        preview_foot.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        ttk.Label(preview_foot, textvariable=self.last_file_var, style="Body.TLabel", wraplength=410).pack(side="left", fill="x", expand=True)
        ttk.Button(preview_foot, text="Open Image", command=self.open_latest_image).pack(side="right", padx=(5, 0))
        ttk.Button(preview_foot, text="Open Folder", command=self.open_save_folder).pack(side="right")

        foot = ttk.Frame(main, style="App.TFrame")
        foot.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        ttk.Label(foot, textvariable=self.status_var, style="Subtitle.TLabel", wraplength=900).pack(side="left")
        # 550px control pane; the preview expands with available window width.
        screen_w, screen_h = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        self.root.geometry(f"{min(1280, max(990, screen_w - 24))}x{min(810, max(630, screen_h - 60))}")
        self.root.minsize(990, 849)
        self.root.after(250, self._refresh_preview)

        # Double-press requires a full key-up between presses; monotonic clock.
        self._hotkey_count = 0
        self._hotkey_last_time = 0.0
        self._hotkey_interval = 0.5
        self._hotkey_cooldown = 1.5
        self._hotkey_cooldown_until = 0.0
        self._key_down = set()
        self._hotkey_lock = threading.Lock()
        self._capture_lock = threading.Lock()
        self._reserved_paths = set()
        self.root.after(40, self._drain_gui_queue)

        # keyboard hook reference
        self._keyboard_hook = None

        # recording state
        self._recording = False
        self._record_thread = None
        self._record_lock = threading.Lock()
        self._record_backend = None  # "cv2" or "imageio" or None
        self._setup_recording_icons()

        # config path (attempt to put next to executable/script; fallback to APPDATA)
        self.config_path = self._get_config_path()

        # load config (sets UI values)
        self.load_config()
        self._record_area_changed()
        if self.show_preview_var.get():
            self._toggle_preview()

        # set up keyboard hook
        self._setup_keyboard_hook()
        self.fkey_combo.config(state="readonly" if self.trigger_var.get() == "F key x 2" else "disabled")
        self.hotkey_hint.config(text=f"Double {self.trigger_var.get().replace(' x 2', '')}")
        self.record_quality_var.set(f"{self.rec_res_var.get()} · {self.rec_fps_var.get()} FPS")

        # Proper cleanup on close
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.bind('<Map>', self._on_root_map, add='+')
        # Startup-only Current-channel check. Never touch active recording.
        self._update_stage = None
        self._update_queued = False
        self.root.after(1800, self._start_update_check)

        # Disable recording controls if no backend available
        if not (_cv2_available or _imageio_available):
            self.start_rec_btn.config(state="disabled")
            self._set_status("Recording disabled: install imageio + imageio-ffmpeg, or OpenCV.")

    def _start_update_check(self):
        """Check server once per launch, asynchronously, without blocking the GUI."""
        if self._closing or not getattr(sys, 'frozen', False):
            return
        try:
            from smart_update import check_background, install_dir
            check_background(install_dir(), lambda version, stage:
                             self._post_gui(self._update_available, version, stage))
        except Exception:
            logging.exception('Auto-update initial check failed')

    def _update_available(self, version, stage):
        if self._closing:
            return
        self._update_stage = stage
        self._set_status('Update ' + version + ' verified and ready to install')
        self._try_start_update()

    def _try_start_update(self):
        if self._closing or self._update_stage is None:
            return
        busy = (self._recording or self._screenshot_running or
                self._video_countdown_job is not None or
                (self._record_thread is not None and self._record_thread.is_alive()))
        if busy:
            # Defer until safe, rather than interrupt machine troubleshooting.
            self._set_status('Update ready — deferred until next application launch')
            return
        from smart_update import launch_external_updater, install_dir
        try:
            launch_external_updater(install_dir(), self._update_stage)
            self._set_status('Installing verified update — SmartScreen will restart')
            self._update_stage = None
            self.root.after(150, self._on_close)
        except Exception as exc:
            logging.exception('Unable to launch external updater')
            self._set_status('Auto-update postponed: ' + str(exc), error=True)

    def _update_quality_label(self):
        """Reflect resolution/FPS changes in the main-panel summary."""
        try:
            self.record_quality_var.set(f"{self.rec_res_var.get()} · {self.rec_fps_var.get()} FPS")
        except tk.TclError:
            pass

    def _preview_resized(self, event=None):
        if self._display_mode == "screenshot" and self._latest_capture is not None:
            self._render_screenshot_preview()

    def _render_screenshot_preview(self):
        if self._latest_capture is None:
            return
        width = max(150, self.preview_holder.winfo_width() - 18)
        height = max(120, self.preview_holder.winfo_height() - 18)
        thumb = self._latest_capture.copy()
        thumb.thumbnail((width, height), Image.Resampling.LANCZOS)
        self._preview_image = ImageTk.PhotoImage(thumb)
        self.preview_label.config(image=self._preview_image, text="")

    def _set_screenshot_preview(self, path):
        try:
            with Image.open(path) as original:
                self._latest_capture = original.convert("RGB")
                self._latest_capture.thumbnail((1600, 1000), Image.Resampling.LANCZOS)
            self._last_capture_path = path
            self._display_mode = "screenshot"
            self.last_file_var.set(Path(path).name)
            self._render_screenshot_preview()
        except Exception as exc:
            logging.exception("Screenshot preview failed")
            self._set_status(f"Saved screenshot, but preview failed: {exc}")

    def open_latest_image(self):
        path = getattr(self, "_last_capture_path", None)
        if path and os.path.isfile(path) and os.name == "nt":
            os.startfile(path)
        elif path:
            messagebox.showinfo("Screenshot", path)
        else:
            messagebox.showinfo("Screenshot", "Capture a screenshot first.")

    def open_save_folder(self):
        path = self.save_dir_var.get().strip()
        if not path:
            return
        try:
            os.makedirs(path, exist_ok=True)
            if os.name == "nt":
                os.startfile(path)
            else:
                messagebox.showinfo("Save folder", path)
        except OSError as exc:
            messagebox.showerror("Save folder", str(exc))

    def _toggle_preview(self):
        if self.show_preview_var.get():
            self._preview_enabled.set()
            if self._recording:
                self._display_mode = "video"
            else:
                self._display_mode = "screenshot"
                self._render_screenshot_preview()
        else:
            self._preview_enabled.clear()
            with self._preview_lock:
                self._preview_frame = None
            self._display_mode = "screenshot"
            self._render_screenshot_preview()

    def _windows_main_hwnd(self):
        """Resolve the actual outer Tk top-level window for Windows taskbar APIs."""
        if os.name != 'nt':
            return None
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.WinDLL('user32', use_last_error=True)
        user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
        user32.GetAncestor.restype = wintypes.HWND
        # winfo_id() is often the Tk client child, not the decorated HWND.
        # wm_frame() is the window manager's frame and is preferred.
        raw_frame = self.root.wm_frame()
        candidate = int(raw_frame, 0) if raw_frame else self.root.winfo_id()
        hwnd = user32.GetAncestor(candidate, 2)  # GA_ROOT
        return int(hwnd or candidate)

    def _minimize_to_taskbar(self, manual=False):
        """Request actual Windows taskbar minimization without hiding the process.

        Tk's event callbacks can be followed by pending window-manager updates;
        running the first request via after_idle avoids that race. A native Win32
        minimize is used only if iconify() was ignored on the target PC.
        """
        if manual:
            self._manual_taskbar_hide = True
            self._auto_record_minimized = False
        self._minimize_pending = True
        self._taskbar_minimize_attempts = 0
        if self._taskbar_minimize_job is not None:
            try:
                self.root.after_cancel(self._taskbar_minimize_job)
            except tk.TclError:
                pass
            self._taskbar_minimize_job = None
        self.root.after_idle(self._do_minimize_to_taskbar)

    def _do_minimize_to_taskbar(self):
        if self._closing or not self._minimize_pending:
            return
        try:
            self.root.iconify()  # Do NOT withdraw: taskbar icon must remain.
            logging.info('Taskbar minimize requested; manual=%s', self._manual_taskbar_hide)
        except tk.TclError:
            logging.exception('Tk taskbar minimization failed')
        self._taskbar_minimize_job = self.root.after(180, self._verify_taskbar_minimized)

    def _verify_taskbar_minimized(self):
        self._taskbar_minimize_job = None
        if self._closing or not self._minimize_pending:
            return
        try:
            tk_minimized = self.root.state() == 'iconic'
            win_minimized = False
            hwnd = self._windows_main_hwnd()
            if hwnd is not None:
                import ctypes
                from ctypes import wintypes
                user32 = ctypes.WinDLL('user32', use_last_error=True)
                user32.IsIconic.argtypes = [wintypes.HWND]
                user32.IsIconic.restype = wintypes.BOOL
                win_minimized = bool(user32.IsIconic(hwnd))
            if tk_minimized or win_minimized:
                self._minimize_pending = False
                logging.info('Taskbar minimized (Tk=%s, Win32=%s)', tk_minimized, win_minimized)
                return
            self._taskbar_minimize_attempts += 1
            if hwnd is not None and self._taskbar_minimize_attempts <= 2:
                import ctypes
                from ctypes import wintypes
                user32 = ctypes.WinDLL('user32', use_last_error=True)
                user32.ShowWindowAsync.argtypes = [wintypes.HWND, ctypes.c_int]
                user32.ShowWindowAsync.restype = wintypes.BOOL
                user32.ShowWindowAsync(hwnd, 6)  # SW_MINIMIZE
                logging.warning('Tk iconify not applied; Win32 ShowWindowAsync(SW_MINIMIZE) hwnd=%s', hwnd)
                self._taskbar_minimize_job = self.root.after(240, self._verify_taskbar_minimized)
            else:
                self._minimize_pending = False
                self._set_status('Unable to minimize to taskbar; see capture log.')
                logging.error('Taskbar minimize failed; state=%s hwnd=%s', self.root.state(), hwnd)
        except Exception:
            self._minimize_pending = False
            logging.exception('Taskbar minimize verification failed')
            self._set_status('Unable to minimize to taskbar; see capture log.')

    def _on_root_map(self, event):
        """Clear manual-hide mode only after a genuine user window restore."""
        if event.widget is not self.root or self._minimize_pending:
            return
        try:
            # Map can also occur during initial creation, so only handle a prior
            # manual hide; state query is deferred until WM has settled.
            if self._manual_taskbar_hide:
                self.root.after_idle(self._check_user_restored)
        except tk.TclError:
            pass

    def _check_user_restored(self):
        if self._closing or self._minimize_pending:
            return
        try:
            if self.root.state() == 'normal':
                self._manual_taskbar_hide = False
                logging.info('Application restored from taskbar by user')
        except tk.TclError:
            pass

    def _setup_recording_icons(self):
        """Prepare a red taskbar recording indicator without a second process."""
        try:
            from PIL import ImageDraw
            normal = Image.new('RGBA', (64, 64), (19, 55, 91, 255))
            draw = ImageDraw.Draw(normal)
            draw.rounded_rectangle((7, 18, 56, 48), radius=7, outline='white', width=4)
            draw.ellipse((25, 25, 39, 39), outline='white', width=3)
            rec = normal.copy()
            draw = ImageDraw.Draw(rec)
            draw.ellipse((40, 0, 63, 23), fill='#ee2626', outline='white', width=2)
            self._normal_icon = ImageTk.PhotoImage(normal)
            self._rec_icon = ImageTk.PhotoImage(rec)
            self.root.iconphoto(False, self._normal_icon)
        except Exception:
            logging.exception('Unable to initialize recording icons')

    def _set_record_state(self, phase, detail=None):
        """Runs only on Tk main thread via _post_gui."""
        self._record_phase = phase
        active = phase == 'Recording'
        colors = {'Ready':'#58677a', 'Preparing':'#ad7516', 'Recording':'#c91b32',
                  'Splitting':'#ad7516', 'Finalizing':'#ad7516', 'Error':'#c91b32',
                  'Stopped':'#58677a'}
        self.rec_indicator.configure(text=('●  REC — RECORDING' if active else
                                           '●  ' + phase.upper()), fg=colors.get(phase, '#58677a'))
        self.root.title(('● REC | ' if active else '') + 'SmartScreen Capture & Recording V1.0')
        try:
            if self._rec_icon and self._normal_icon:
                self.root.iconphoto(False, self._rec_icon if active else self._normal_icon)
        except Exception:
            pass
        if detail:
            self._set_status(detail)
        if active and os.name == 'nt':
            self._flash_taskbar()

    def _flash_taskbar(self):
        """Taskbar-only attention cue; never overlays the HMI being recorded."""
        try:
            import ctypes
            from ctypes import wintypes
            class FLASHWINFO(ctypes.Structure):
                _fields_ = [('cbSize', wintypes.UINT), ('hwnd', wintypes.HWND),
                            ('dwFlags', wintypes.DWORD), ('uCount', wintypes.UINT),
                            ('dwTimeout', wintypes.DWORD)]
            info = FLASHWINFO(ctypes.sizeof(FLASHWINFO), self.root.winfo_id(), 0x00000002, 3, 0)
            ctypes.windll.user32.FlashWindowEx(ctypes.byref(info))
        except Exception:
            logging.debug('Windows taskbar flash unavailable', exc_info=True)

    def _refresh_preview(self):
        if self._closing:
            return
        if self._preview_enabled.is_set():
            with self._preview_lock:
                frame, self._preview_frame = self._preview_frame, None
            if frame is not None:
                try:
                    self._display_mode = "video"
                    width = max(160, self.preview_holder.winfo_width() - 18)
                    height = max(120, self.preview_holder.winfo_height() - 18)
                    frame.thumbnail((width, height), Image.Resampling.BILINEAR)
                    self._preview_image = ImageTk.PhotoImage(frame)
                    self.preview_label.config(image=self._preview_image, text="")
                except Exception:
                    logging.exception("Video preview render error")
        with self._record_lock:
            active, frames, started = self._recording, self._record_frames, self._record_start_monotonic
            part, nbytes, path = self._record_part, self._record_segment_bytes, self._record_path
        if started is not None:
            elapsed = max(0, int(time.monotonic() - started))
            clock = f"{elapsed//3600:02}:{(elapsed//60)%60:02}:{elapsed%60:02}"
        else:
            clock = "00:00:00"
        self.record_stats_var.set(f"{self._record_phase} · {clock} · {frames} frames")
        if part:
            self.record_segment_var.set(f"Part {part:02}  ·  {nbytes/1_000_000:.1f} MB / 1000 MB  ·  {Path(path).name}")
        if not active and self._display_mode == "video":
            self._display_mode = "screenshot"
            self._render_screenshot_preview()
        self.root.after(250, self._refresh_preview)

    def _get_config_path(self):
        """Always store config.json next to the EXE (or .py during development).

        No AppData or working-directory fallback: operators can move the complete
        portable application folder without losing or duplicating settings.
        """
        if getattr(sys, "frozen", False):
            base_dir = Path(sys.executable).resolve().parent
        else:
            base_dir = Path(__file__).resolve().parent
        return str(base_dir / self.CONFIG_FILE_NAME)

    def _load_app_icon(self):
        """Set application/taskbar icon and cache a PNG for the small UI logo."""
        self._header_logo = None
        icon_path = find_resource('assets/ASC_Logo.ico', 'SiliconBox.ico')
        image_path = find_resource('assets/ASC_Logo.png', 'SiliconBox.png')
        if icon_path and os.name == 'nt':
            try:
                self.root.iconbitmap(str(icon_path))
            except Exception:
                pass
        if image_path:
            try:
                image = Image.open(image_path).convert('RGBA')
                image.thumbnail((44, 44), Image.Resampling.LANCZOS)
                self._header_logo = ImageTk.PhotoImage(image)
                self._icon_photo = self._header_logo
                self.root.iconphoto(False, self._icon_photo)
            except Exception:
                pass

    def browse_folder(self):
        selected = filedialog.askdirectory()
        if selected:
            self.save_dir_var.set(selected)

    def _populate_monitor_list(self):
        """
        Populate self._monitors_cache and monitor_combo values.
        Uses mss if available to enumerate monitors (recommended).
        Otherwise attempts a minimal Windows fallback (via ctypes) to discover monitors;
        if that fails, shows just "All (virtual)".
        """
        monitors_display = []
        self._monitors_cache = []

        if MSS_AVAILABLE:
            try:
                with mss.MSS() as s:
                    # s.monitors[0] is the virtual combined screen; s.monitors[1:] are physical monitors
                    monitors = s.monitors
                    # first entry: All (virtual)
                    monitors_display.append("All (virtual)")
                    self._monitors_cache.append({"id": 0, "name": "All (virtual)", "bbox": monitors[0]})
                    for idx, m in enumerate(monitors[1:], start=1):
                        name = f"Monitor {idx} ({m['width']}x{m['height']})"
                        monitors_display.append(name)
                        # store bbox as (left, top, right, bottom)
                        bbox = (m["left"], m["top"], m["left"] + m["width"], m["top"] + m["height"])
                        self._monitors_cache.append({"id": idx, "name": name, "bbox": bbox})
            except Exception:
                # fallback to limited option
                monitors_display = ["All (virtual)"]
                self._monitors_cache = [{"id": 0, "name": "All (virtual)", "bbox": None}]
        else:
            # Try a simple Windows-only monitor enumeration (best-effort) using ctypes
            if os.name == "nt":
                try:
                    import ctypes
                    user32 = ctypes.windll.user32
                    # Ensure process is dpi aware to get physical coordinates if possible
                    try:
                        ctypes.windll.shcore.SetProcessDpiAwareness(2)
                    except Exception:
                        try:
                            user32.SetProcessDPIAware()
                        except Exception:
                            pass

                    # EnumDisplayMonitors via ctypes: collect monitor rectangles
                    MONITORS = []

                    def _monitor_enum(hMonitor, hdcMonitor, lprcMonitor, dwData):
                        r = ctypes.cast(lprcMonitor, ctypes.POINTER(ctypes.c_long * 4)).contents
                        left = int(r[0]); top = int(r[1]); right = int(r[2]); bottom = int(r[3])
                        MONITORS.append((left, top, right, bottom))
                        return 1

                    MonitorEnumProc = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong, ctypes.POINTER(ctypes.c_long * 4), ctypes.c_double)
                    user32.EnumDisplayMonitors(0, 0, MonitorEnumProc(_monitor_enum), 0)

                    if MONITORS:
                        monitors_display.append("All (virtual)")
                        self._monitors_cache.append({"id": 0, "name": "All (virtual)", "bbox": None})
                        for idx, rect in enumerate(MONITORS, start=1):
                            left, top, right, bottom = rect
                            w = right - left
                            h = bottom - top
                            name = f"Monitor {idx} ({w}x{h})"
                            monitors_display.append(name)
                            self._monitors_cache.append({"id": idx, "name": name, "bbox": rect})
                    else:
                        monitors_display = ["All (virtual)"]
                        self._monitors_cache = [{"id": 0, "name": "All (virtual)", "bbox": None}]
                except Exception:
                    monitors_display = ["All (virtual)"]
                    self._monitors_cache = [{"id": 0, "name": "All (virtual)", "bbox": None}]
            else:
                # Non-windows and no mss: provide only All
                monitors_display = ["All (virtual)"]
                self._monitors_cache = [{"id": 0, "name": "All (virtual)", "bbox": None}]

        # apply to combobox
        try:
            self.monitor_combo.config(values=monitors_display)
            # if empty select first
            if monitors_display:
                # try to preserve previous selection if still present
                cur = self.monitor_list_var.get()
                if cur in monitors_display:
                    self.monitor_combo.set(cur)
                else:
                    self.monitor_combo.current(0)
        except Exception:
            pass

    def capture_now(self):
        # The GUI is minimized before capture, avoiding a screenshot of this application.
        # Delay also gives operators a chance to bring the equipment HMI to the front.
        if getattr(self, '_selection_active', False):
            self._set_status('Finish or cancel the current selection first.')
            return
        if self._screenshot_running:
            self._set_status("Screenshot already pending; wait for completion.")
            return
        try:
            args = self._capture_options()
            args['delay'] = max(0, min(60, int(args['delay'])))
            args['use_delay'] = args['use_delay'] and args['delay'] > 0
        except (ValueError, tk.TclError) as exc:
            self._set_status(f"Invalid screenshot delay: {exc}")
            return
        self._screenshot_running = True
        self.capture_btn.config(state="disabled")
        args['restore_window'] = bool(self.hide_during_capture_var.get())
        if args['restore_window']:
            self._minimize_to_taskbar()
        threading.Thread(target=self._capture_screenshot_thread, args=(args,), daemon=True).start()

    def _finish_screenshot(self, restore_window):
        self._screenshot_running = False
        self.capture_btn.config(state="normal")
        if restore_window and not self._closing and not self._manual_taskbar_hide:
            self._minimize_pending = False
            self.root.deiconify()
            self.root.lift()

    def _capture_options(self):
        return dict(save_as=self.save_as_var.get().strip(), save_dir=self.save_dir_var.get().strip(),
                    use_delay=bool(self.use_delay_var.get()),
                    delay=int(self.delay_seconds_var.get()) if self.use_delay_var.get() else 0,
                    monitor_enabled=bool(self.use_monitor_select_var.get()),
                    monitor_name=self.monitor_list_var.get(),
                    monitors=list(self._monitors_cache), scale=self.scale_var.get())

    def _reserve_filename(self, directory, base, extension, recording=False):
        """Atomically reserve a unique filename; named captures use 01, 02..."""
        base = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', base.strip()).rstrip('. ') or 'UNNAMED'
        # The default-generated names include a timestamp; user-entered names do not.
        automatic = bool(re.fullmatch(r'(Screenshot|Recording)_\d{8}_\d{6}', base))
        index = 0 if automatic else 1
        while True:
            suffix = '' if index == 0 else (f'_{index:02d}' if automatic else f'{index:02d}')
            path = os.path.join(directory, f'{base}{suffix}.{extension}')
            try:
                fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o666)
                os.close(fd)
                return path
            except FileExistsError:
                index = max(1, index + 1)

    def _post_gui(self, callback, *args):
        if not self._closing:
            self._gui_queue.put((callback, args))

    def _drain_gui_queue(self):
        if self._closing:
            return
        for _ in range(100):
            try:
                cb, args = self._gui_queue.get_nowait()
            except queue.Empty:
                break
            try:
                cb(*args)
            except Exception:
                logging.exception('GUI callback failed')
        self.root.after(40, self._drain_gui_queue)

    def _capture_screenshot_thread(self, options):
        try:
            self._capture_screenshot_work(options)
        finally:
            if options.get('restore_window'):
                self._post_gui(self._finish_screenshot, True)
            elif self._screenshot_running:
                self._post_gui(self._finish_screenshot, False)

    def _capture_screenshot_work(self, options):
        """
        Worker thread that optionally waits for a configured delay and then captures the screen.
        This function reads the Operation Mode, Save As and Save folder from the UI variables at the time
        the capture starts.
        """
        save_as = options['save_as']
        save_dir = options['save_dir']

        if not save_dir:
            self._set_status("Please choose a save folder.", error=True)
            return

        # Check delay
        use_delay = options['use_delay']
        try:
            delay = options['delay']
        except Exception:
            delay = 0

        if use_delay and delay > 0:
            # Provide a simple countdown in the status bar so the user knows capture is pending.
            for remaining in range(delay, 0, -1):
                self._set_status(f"Capturing in {remaining} second(s)...")
                time.sleep(1)

        target_dir = save_dir
        try:
            os.makedirs(target_dir, exist_ok=True)
        except Exception as e:
            self._set_status(f"Failed to create directory: {e}", error=True)
            return

        # Determine next sequential filename for this operation mode using save_as override
        try:
            full_path = self._reserve_filename(target_dir, (save_as if save_as else f"Screenshot_{datetime.now():%Y%m%d_%H%M%S}"), 'png')
        except Exception as e:
            self._set_status(f"Failed to determine filename: {e}", error=True)
            return

        # Decide which monitor to capture (all by default)
        use_monitor_select = options['monitor_enabled']
        selected_monitor_idx = 0
        selected_bbox = None
        if use_monitor_select:
            try:
                # selected value is a display string; find matching cached monitor
                sel = options['monitor_name']
                for mon in options['monitors']:
                    if mon["name"] == sel:
                        selected_monitor_idx = mon["id"]
                        selected_bbox = mon.get("bbox")
                        break
                else:
                    # fallback to 0 (all)
                    selected_monitor_idx = 0
                    selected_bbox = None
            except Exception:
                selected_monitor_idx = 0
                selected_bbox = None
        else:
            selected_monitor_idx = 0
            selected_bbox = None

        # Determine requested scale factor (default 1.0)
        try:
            scale_text = options['scale'].strip().lower()
            if scale_text.endswith("x"):
                scale_text = scale_text[:-1]
            scale_factor = float(scale_text) if scale_text else 1.0
            if scale_factor <= 0:
                scale_factor = 1.0
        except Exception:
            scale_factor = 1.0

        # Capture using mss if possible and if user selected a specific monitor
        try:
            if MSS_AVAILABLE:
                with mss.MSS() as s:
                    monitors = s.monitors
                    if use_monitor_select and selected_monitor_idx != 0:
                        # If requested monitor index exists, capture it
                        if 0 < selected_monitor_idx < len(monitors):
                            mon = monitors[selected_monitor_idx]
                        else:
                            # invalid index; fallback to virtual
                            mon = monitors[0]
                    else:
                        # capture virtual combined desktop
                        mon = monitors[0]

                    s_img = s.grab(mon)
                    # Convert mss image to PIL Image
                    try:
                        img = Image.frombytes("RGB", s_img.size, s_img.rgb)
                    except Exception:
                        # Some mss builds may provide BGRA; try using raw and convert
                        try:
                            img = Image.frombuffer("RGBA", s_img.size, s_img.bgra, "raw", "BGRA", 0, 1).convert("RGB")
                        except Exception:
                            # last resort: use to_png to a temporary file and open via PIL
                            import io
                            png_bytes = mss.tools.to_png(s_img.rgb, s_img.size)
                            img = Image.open(io.BytesIO(png_bytes)).convert("RGB")

                    # Resize (scale) if requested
                    if scale_factor != 1.0:
                        new_size = (max(1, int(img.width * scale_factor)), max(1, int(img.height * scale_factor)))
                        img = img.resize(new_size, Image.LANCZOS)

                    img.save(full_path, "PNG")
            else:
                # MSS not available: try PIL.ImageGrab
                # If user requested a specific monitor and we have bbox info (from cache), pass bbox to ImageGrab
                if use_monitor_select and selected_monitor_idx != 0 and selected_bbox:
                    try:
                        left, top, right, bottom = selected_bbox
                        img = ImageGrab.grab(bbox=(left, top, right, bottom))
                    except Exception:
                        # fallback to grab() of entire virtual screen
                        img = ImageGrab.grab()
                else:
                    img = ImageGrab.grab()

                # Resize (scale) if requested
                if scale_factor != 1.0:
                    new_size = (max(1, int(img.width * scale_factor)), max(1, int(img.height * scale_factor)))
                    img = img.resize(new_size, Image.LANCZOS)

                img.save(full_path, "PNG")

            # Update status and show temporary popup (run in GUI thread)
            self._set_status(f"Saved screenshot: {full_path}")
            self._post_gui(self._set_screenshot_preview, full_path)
            # Preview and status provide nonintrusive confirmation, without focus-stealing popup.
        except Exception as e:
            # Capture may fail (black image or API error). Provide helpful status message.
            try:
                if os.path.isfile(full_path) and os.path.getsize(full_path) == 0:
                    os.remove(full_path)
            except Exception:
                pass
            self._set_status(f"Failed to capture/save screenshot: {e}", error=True)

    def _show_temp_popup(self, text, duration_ms=1000):
        """
        Create a small borderless topmost popup and aggressively try to bring it to the
        foreground so it doesn't get hidden behind other windows.

        Strategies used (fall back safely if unavailable):
        - Toplevel with overrideredirect and attributes("-topmost", True)
        - popup.lift(), popup.focus_force()
        - call Windows API SetWindowPos(HWND_TOPMOST) and SetForegroundWindow via ctypes
        - keep it for duration_ms then destroy
        """
        def create_popup():
            popup = tk.Toplevel(self.root)
            popup.overrideredirect(True)  # no window decorations
            popup.attributes("-topmost", True)
            # style
            frame = tk.Frame(popup, bg="#333333", bd=1, relief="solid")
            frame.pack(fill=tk.BOTH, expand=True)
            label = tk.Label(
                frame, text=text, fg="white", bg="#333333",
                font=("Segoe UI", 12, "bold"), padx=20, pady=10
            )
            label.pack()

            # ensure geometry is calculated
            popup.update_idletasks()
            pw = popup.winfo_reqwidth()
            ph = popup.winfo_reqheight()
            # compute center over the main window
            try:
                rx = self.root.winfo_rootx()
                ry = self.root.winfo_rooty()
                rw = self.root.winfo_width()
                rh = self.root.winfo_height()
                x = rx + max((rw - pw) // 2, 0)
                y = ry + max((rh - ph) // 2, 0)
            except Exception:
                # fallback to screen center
                sw = popup.winfo_screenwidth()
                sh = popup.winfo_screenheight()
                x = (sw - pw) // 2
                y = (sh - ph) // 2

            popup.geometry(f"{pw}x{ph}+{x}+{y}")

            # Try to bring popup to front: multiple attempts to maximize chance of visibility
            try:
                popup.lift()
                popup.attributes("-topmost", True)
                popup.focus_force()
                popup.update()
            except Exception:
                pass

            # Attempt to call Windows API to set it as foreground/topmost (best-effort)
            try:
                # only attempt on Windows
                if os.name == "nt":
                    hwnd = popup.winfo_id()
                    import ctypes
                    user32 = ctypes.windll.user32
                    SWP_NOMOVE = 0x0002
                    SWP_NOSIZE = 0x0001
                    HWND_TOPMOST = -1
                    # Set the window position to topmost (no move/no size)
                    user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE)
                    # Try to set foreground
                    try:
                        user32.SetForegroundWindow(hwnd)
                    except Exception:
                        # sometimes SetForegroundWindow can fail due to Windows focus rules;
                        # as an alternative, try ShowWindow + SetForegroundWindow sequence
                        try:
                            SW_SHOW = 5
                            user32.ShowWindow(hwnd, SW_SHOW)
                            user32.SetForegroundWindow(hwnd)
                        except Exception:
                            pass
            except Exception:
                # swallow all failures here — popup still exists as topmost Toplevel
                pass

            # schedule auto-close
            popup.after(duration_ms, popup.destroy)

        # schedule creation on main thread
        self._post_gui(create_popup)

    def _set_status(self, text, error=False):
        self._post_gui(self.status_var.set, text)

    def _keyboard_event(self, event):
        """Hook callback may run off the GUI thread; do not touch Tk here."""
        try:
            event_type = event.event_type
            key = (event.name or '').lower()
            now = time.monotonic()
            # Using saved plain strings avoids accessing Tk from the hook thread.
            with self._hotkey_lock:
                trigger = self._active_trigger
                chosen_f = self._active_fkey
                key_id = key
                relevant = ((trigger == 'Ctrl x 2' and key in ('ctrl', 'left ctrl', 'right ctrl')) or
                            (trigger == 'Shift x 2' and key in ('shift', 'left shift', 'right shift')) or
                            (trigger == 'F key x 2' and key == chosen_f))
                if not relevant:
                    # Pressing a different key cancels a pending modifier-double-tap.
                    if event_type == 'down' and self._hotkey_count:
                        self._hotkey_count = 0
                    return
                if event_type == 'up':
                    self._key_down.discard(key_id)
                    return
                if event_type != 'down' or key_id in self._key_down:
                    return  # Auto-repeat must never count as second press.
                self._key_down.add(key_id)
                if now < self._hotkey_cooldown_until:
                    return
                if self._hotkey_count == 1 and now - self._hotkey_last_time <= self._hotkey_interval:
                    self._hotkey_count = 0
                    self._hotkey_cooldown_until = now + self._hotkey_cooldown
                    self._post_gui(self.capture_now)
                else:
                    self._hotkey_count = 1
                    self._hotkey_last_time = now
        except Exception:
            logging.exception('Keyboard hook error')

    def _setup_keyboard_hook(self):
        try:
            # Clear any existing hooks first
            try:
                if self._keyboard_hook is not None:
                    keyboard.unhook(self._keyboard_hook)
            except Exception:
                keyboard.unhook_all()

            with self._hotkey_lock:
                self._active_trigger = self.trigger_var.get()
                self._active_fkey = self.fkey_var.get().lower()
                self._hotkey_count = 0
                self._key_down.clear()
            self._keyboard_hook = keyboard.hook(self._keyboard_event)
            self._set_status(f"Ready. Trigger: {self.trigger_var.get() or 'None'}")
        except Exception as e:
            self._set_status(f"Failed to register keyboard hook: {e}", error=True)
            messagebox.showwarning(
                "Hook registration failed",
                f"Could not register global keyboard hook.\n\n{e}\n\nYou can still use the 'Capture Now' button."
            )

    def _on_trigger_change(self):
        # enable/disable fkey chooser based on trigger selection
        trig = self.trigger_var.get()
        if trig == "F key x 2":
            self.fkey_combo.config(state="readonly")
            if not self.fkey_var.get():
                self.fkey_var.set(self.FK_KEYS[0])
        else:
            self.fkey_combo.config(state="disabled")
        # Recreate the hook so new trigger selection takes effect immediately
        self._setup_keyboard_hook()

    def _on_delay_toggle(self):
        # Enable/disable spinbox depending on checkbox
        if self.use_delay_var.get():
            self.delay_spin.config(state="normal")
        else:
            self.delay_spin.config(state="disabled")

    def _on_monitor_toggle(self):
        if self.use_monitor_select_var.get():
            # enable the combobox and (re)populate monitors
            self._populate_monitor_list()
            self.monitor_combo.config(state="readonly")
        else:
            self.monitor_combo.config(state="disabled")

    def save_config(self):
        cfg = {
            "save_as": self.save_as_var.get().strip(),
            "save_dir": self.save_dir_var.get().strip(),
            "trigger": self.trigger_var.get(),
            "fkey": self.fkey_var.get(),
            "hotkey_interval": self._hotkey_interval,
            "use_delay": bool(self.use_delay_var.get()),
            "delay_seconds": int(self.delay_seconds_var.get() or 0),
            "video_delay_seconds": int(self.video_delay_seconds_var.get() or 0),
            "hide_during_capture": bool(self.hide_during_capture_var.get()),
            "use_monitor_select": bool(self.use_monitor_select_var.get()),
            "selected_monitor": self.monitor_list_var.get(),
            "save_scale": self.scale_var.get(),
            "recording_fps": int(self.rec_fps_var.get()),
            "recording_resolution": self.rec_res_var.get(),
            "show_preview": bool(self.show_preview_var.get()),
            "record_area_mode": self.record_area_mode_var.get(),
            "record_region": list(self.record_region) if self.record_region else None,
        }
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2)
            self._set_status(f"Settings saved to {self.config_path}")
        except Exception as e:
            self._set_status(f"Cannot save config beside EXE: {e}. Move application to a writable folder.", error=True)

    def load_config(self):
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                # load save_as if present
                self.save_as_var.set(cfg.get("save_as", ""))
                self.save_dir_var.set(cfg.get("save_dir") or str(Path.home() / "Pictures" / "SmartScreen Captures"))
                trigger = cfg.get("trigger", "")
                if trigger in self.TRIGGER_OPTIONS:
                    self.trigger_var.set(trigger)
                else:
                    self.trigger_var.set(self.TRIGGER_OPTIONS[0])
                fkey = cfg.get("fkey", "")
                if fkey in self.FK_KEYS:
                    self.fkey_var.set(fkey)
                else:
                    self.fkey_var.set(self.FK_KEYS[0])
                if cfg.get("hotkey_interval"):
                    try:
                        self._hotkey_interval = max(0.2, min(0.8, float(cfg.get("hotkey_interval"))))
                    except Exception:
                        pass
                # load delay settings
                try:
                    self.use_delay_var.set(bool(cfg.get("use_delay", True)))
                except Exception:
                    self.use_delay_var.set(False)
                try:
                    self.delay_seconds_var.set(int(cfg.get("delay_seconds", 3)))
                except Exception:
                    self.delay_seconds_var.set(3)
                try:
                    self.video_delay_seconds_var.set(max(0, min(60, int(cfg.get("video_delay_seconds", 3)))))
                except (ValueError, TypeError):
                    self.video_delay_seconds_var.set(3)
                self.hide_during_capture_var.set(bool(cfg.get("hide_during_capture", True)))
                # load monitor selection settings
                try:
                    self.use_monitor_select_var.set(bool(cfg.get("use_monitor_select", False)))
                except Exception:
                    self.use_monitor_select_var.set(False)
                # populate monitors and set selection
                self._populate_monitor_list()
                sel_mon = cfg.get("selected_monitor", "")
                if sel_mon:
                    self.monitor_list_var.set(sel_mon)
                # load scale
                try:
                    scale_val = cfg.get("save_scale", "1.0x")
                    if scale_val:
                        self.scale_var.set(scale_val)
                except Exception:
                    self.scale_var.set("1.0x")
                self.show_preview_var.set(bool(cfg.get("show_preview", False)))
                region = cfg.get('record_region')
                if isinstance(region, list) and len(region) == 4:
                    try:
                        self.record_region=tuple(int(v) for v in region)
                    except (TypeError, ValueError):
                        self.record_region=None
                self.record_area_mode_var.set(cfg.get('record_area_mode', 'Full Screen')
                         if cfg.get('record_area_mode') in ('Full Screen', 'Custom Region', 'Selected Window') else 'Full Screen')
                # load recording settings
                try:
                    fps = int(cfg.get("recording_fps", 15))
                    if fps < 1:
                        fps = 15
                    self.rec_fps_var.set(fps)
                except Exception:
                    self.rec_fps_var.set(15)
                try:
                    res = cfg.get("recording_resolution", "Native")
                    if res in ("Native", "1080p", "1440p"):
                        self.rec_res_var.set(res)
                    else:
                        self.rec_res_var.set("Native")
                except Exception:
                    self.rec_res_var.set("Native")
                # ensure spin state matches checkbox
                if self.use_delay_var.get():
                    self.delay_spin.config(state="normal")
                else:
                    self.delay_spin.config(state="disabled")
                # monitor combobox state
                if self.use_monitor_select_var.get():
                    self.monitor_combo.config(state="readonly")
                else:
                    self.monitor_combo.config(state="disabled")
            else:
                # set defaults
                self.trigger_var.set(self.TRIGGER_OPTIONS[0])
                self.fkey_var.set(self.FK_KEYS[0])
                if self.trigger_var.get() == "F key x 2":
                    self.fkey_combo.config(state="readonly")
                else:
                    self.fkey_combo.config(state="disabled")
                self.use_delay_var.set(True)
                self.delay_seconds_var.set(3)
                self.video_delay_seconds_var.set(3)
                self.hide_during_capture_var.set(True)
                self.delay_spin.config(state="normal")
                self.use_monitor_select_var.set(False)
                self._populate_monitor_list()
                self.monitor_combo.config(state="disabled")
                self.scale_var.set("1.0x")
                # recording defaults
                self.rec_fps_var.set(15)
                self.rec_res_var.set("Native")
        except Exception as e:
            self._set_status(f"Failed to load config: {e}", error=True)

    # Preview setting is applied after load_config on startup.

    def show_about(self):
        extra = ""
        if MSS_AVAILABLE:
            extra = "\n\nmss library detected: per-monitor capture available."
        else:
            extra = "\n\nmss library NOT detected: per-monitor capture may be less reliable. Install with: pip install mss"

        rec_extra = ""
        rec_extra = (f"\n\nOpenCV: {_cv2_available}, imageio: {_imageio_available}, "
                     f"FFmpeg: {ffmpeg_executable() or 'not detected'}")

        messagebox.showinfo("About", self.ABOUT_TEXT + extra + rec_extra)

    def _clear_hook(self):
        try:
            if self._keyboard_hook is not None:
                keyboard.unhook(self._keyboard_hook)
                self._keyboard_hook = None
            else:
                keyboard.unhook_all()
        except Exception:
            pass

    def _on_close(self):
        if self._video_countdown_job is not None:
            self.root.after_cancel(self._video_countdown_job)
            self._video_countdown_job = None
        # Save settings on close
        try:
            self.save_config()
        except Exception:
            pass
        # cleanup keyboard hooks then close
        self._clear_hook()
        # ensure recording stopped
        try:
            if self._recording:
                self._set_status("Stopping recording before exit...")
                self.stop_recording(wait=False)
        except Exception:
            pass
        if self._record_thread is not None and self._record_thread.is_alive():
            self._set_status('Finishing video file before exit...')
            self.root.after(200, self._finish_close)
            return
        self._closing = True
        self.root.destroy()

    def _finish_close(self):
        if self._record_thread is not None and self._record_thread.is_alive():
            self.root.after(200, self._finish_close)
            return
        self._closing = True
        self.root.destroy()

    # ---------- Fixed recording region ----------
    def _record_area_changed(self, event=None):
        mode = self.record_area_mode_var.get()
        custom = mode == 'Custom Region'
        window = mode == 'Selected Window'
        self.select_region_btn.configure(
            text='Select Window' if window else 'Select Area',
            command=self.select_record_window if window else self.select_record_area,
            state='normal' if custom or window else 'disabled')
        self.show_region_btn.configure(
            text='Show Window' if window else 'Show Area',
            command=self.show_record_window if window else self.show_record_area,
            state='normal' if (window and self.selected_window_hwnd) or
                  (custom and self.record_region) else 'disabled')
        if window:
            self.record_area_summary.set(
                f'Window: {self.selected_window_title} (independent HMI capture (WGC x64))' if self.selected_window_hwnd
                else 'No window selected — click Select Window')
        elif custom and self.record_region:
            x, y, w, h = self.record_region
            self.record_area_summary.set(f'Region: X={x}, Y={y}  ·  {w} × {h} px')
        elif custom:
            self.record_area_summary.set('No region selected — click Select Area')
        else:
            self.record_area_summary.set('Full selected monitor / desktop')

    @staticmethod
    def _window_rect(hwnd):
        """Position of a live, nonminimized top-level Windows application window."""
        if os.name != 'nt':
            raise RuntimeError('Selected Window requires Windows')
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.WinDLL('user32', use_last_error=True)
        user32.IsWindow.argtypes = [wintypes.HWND]
        user32.IsWindow.restype = wintypes.BOOL
        user32.IsIconic.argtypes = [wintypes.HWND]
        user32.IsIconic.restype = wintypes.BOOL
        user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        user32.GetWindowRect.restype = wintypes.BOOL
        if not hwnd or not user32.IsWindow(hwnd):
            raise RuntimeError('Selected window has closed. Recording stopped.')
        if user32.IsIconic(hwnd):
            raise RuntimeError('Selected window is minimized; recording stopped.')
        rect = wintypes.RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            raise RuntimeError('Cannot read the selected window position')
        # Windows' GetWindowRect may include invisible resize borders, making
        # a maximized window appear outside the physical monitor. DWM reports
        # its visible border bounds when available (Vista or later).
        try:
            dwm = ctypes.WinDLL('dwmapi', use_last_error=True)
            dwm.DwmGetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD,
                                                  ctypes.c_void_p, wintypes.DWORD]
            dwm.DwmGetWindowAttribute.restype = ctypes.c_long
            visible = wintypes.RECT()
            if dwm.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(visible),
                                         ctypes.sizeof(visible)) == 0:
                if visible.right > visible.left and visible.bottom > visible.top:
                    rect = visible
        except (AttributeError, OSError):
            pass
        x, y = rect.left, rect.top
        w, h = rect.right - x, rect.bottom - y
        if w < 32 or h < 32:
            raise RuntimeError('Selected window dimensions are too small')
        return (x, y, w, h)

    @staticmethod
    def _window_at_point(x, y, ignore_hwnd=0):
        """Hit-test visible external top-level HWNDs in desktop Z-order.

        The fullscreen Tk selection overlay covers the desktop, so Windows'
        WindowFromPoint would report that overlay. EnumWindows + process-ID
        exclusion avoids selecting SmartScreen itself or any Tk popup.
        """
        if os.name != 'nt':
            raise RuntimeError('Window selection is supported on Windows only')
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.WinDLL('user32', use_last_error=True)
        callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
        user32.EnumWindows.restype = wintypes.BOOL
        user32.IsWindowVisible.argtypes = [wintypes.HWND]
        user32.IsWindowVisible.restype = wintypes.BOOL
        user32.IsIconic.argtypes = [wintypes.HWND]
        user32.IsIconic.restype = wintypes.BOOL
        user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        user32.GetWindowTextLengthW.restype = ctypes.c_int
        user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        user32.GetWindowTextW.restype = ctypes.c_int
        user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        user32.GetWindowRect.restype = wintypes.BOOL
        selected = []
        own_pid = os.getpid()

        def visit(hwnd, _):
            if hwnd == ignore_hwnd or not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
                return True
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value == own_pid:
                return True
            title_length = user32.GetWindowTextLengthW(hwnd)
            if title_length == 0:
                return True  # desktop, anonymous child and utility windows
            rect = wintypes.RECT()
            if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                return True
            if not (rect.left <= x < rect.right and rect.top <= y < rect.bottom):
                return True
            if rect.right - rect.left < 32 or rect.bottom - rect.top < 32:
                return True
            title = ctypes.create_unicode_buffer(title_length + 1)
            user32.GetWindowTextW(hwnd, title, title_length + 1)
            if title.value.strip():
                selected.append((int(hwnd), title.value.strip()))
                return False  # EnumWindows is ordered front-to-back
            return True

        cb = callback_type(visit)
        user32.EnumWindows(cb, 0)
        return selected[0] if selected else None

    def _begin_record_selection(self):
        """Own one selector session and remember the visible window's WM state."""
        if getattr(self, '_selection_active', False):
            self._set_status('Finish or cancel the current selection first.')
            return False
        if self._screenshot_running:
            self._set_status('Wait for the pending screenshot before selecting an area.')
            return False
        previous = self.root.state()
        self._selector_restore_state = 'zoomed' if previous == 'zoomed' else 'normal'
        self._selector_overlay = None
        self._selector_job = None
        # An explicit selection action supersedes an earlier minimize request.
        self._manual_taskbar_hide = False
        self._minimize_pending = False
        if self._taskbar_minimize_job is not None:
            self.root.after_cancel(self._taskbar_minimize_job)
            self._taskbar_minimize_job = None
        self._selection_active = True
        try:
            self.root.withdraw()
        except Exception:
            self._restore_after_record_selection()
            raise
        return True

    def _restore_after_record_selection(self):
        """Close the overlay exactly once and always make the application reachable."""
        if not getattr(self, '_selection_active', False):
            return
        self._selection_active = False
        if self._selector_job is not None:
            try:
                self.root.after_cancel(self._selector_job)
            except tk.TclError:
                pass
            self._selector_job = None
        overlay, self._selector_overlay = self._selector_overlay, None
        if overlay is not None:
            try:
                overlay.destroy()
            except tk.TclError:
                pass
        if self._closing:
            return
        self._manual_taskbar_hide = False
        self._minimize_pending = False
        self.root.deiconify()
        if self._selector_restore_state == 'zoomed':
            self.root.state('zoomed')
        self.root.lift()
        self.root.focus_set()

    def select_record_window(self):
        if self._recording or self._video_countdown_job is not None:
            self._set_status('Stop recording before selecting another window.')
            return
        if os.name != 'nt':
            self._set_status('Selected Window requires Windows.', error=True)
            return
        if self._begin_record_selection():
            self._selector_job = self.root.after(350, self._create_window_selector)

    def _create_window_selector(self):
        """Highlight the HWND under the cursor on a frozen desktop snapshot.

        A single periodic mouse-position check is used; no global mouse hook,
        new thread, or second screen grab is required. The overlay itself is
        excluded via process-ID filtering during window hit-testing.
        """
        self._selector_job = None
        if self._closing or not getattr(self, '_selection_active', False):
            return
        overlay = None
        try:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.WinDLL('user32', use_last_error=True)
            user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
            user32.GetCursorPos.restype = wintypes.BOOL
            bounds = self._record_area_bounds()
            left, top, width, height = bounds
            background = self._capture_region_pixels(bounds)
            overlay = tk.Toplevel(self.root)
            self._selector_overlay = overlay
            overlay.overrideredirect(True)
            overlay.attributes('-topmost', True)
            overlay.geometry(f'{width}x{height}{left:+d}{top:+d}')
            canvas = tk.Canvas(overlay, highlightthickness=0, cursor='crosshair')
            canvas.pack(fill='both', expand=True)
            preview = ImageTk.PhotoImage(background)
            canvas.create_image(0, 0, image=preview, anchor='nw')
            canvas.preview_image = preview

            # A non-interactive outline shows the detected window boundaries.
            # The source desktop snapshot is taken before the overlay appears.
            outline = canvas.create_rectangle(0, 0, 0, 0,
                        outline='#27e677', width=4, state='hidden')
            bar = canvas.create_rectangle(0, 0, width, 39,
                        fill='#172335', outline='')
            instruction = canvas.create_text(width // 2, 19,
                        text='Move mouse: Highlight window   |   Left-click: Select   |   Esc: Cancel',
                        fill='white', font=('Segoe UI', 11, 'bold'))
            name_text = canvas.create_text(12, 52, anchor='nw',
                        text='Move mouse onto the HMI window',
                        fill='#39f28b', font=('Segoe UI', 12, 'bold'))
            state = {'hover': None, 'closed': False, 'after': None}

            def close(selection=None, error=None):
                if state['closed']:
                    return
                state['closed'] = True
                if state['after'] is not None:
                    try:
                        overlay.after_cancel(state['after'])
                    except tk.TclError:
                        pass
                self._restore_after_record_selection()
                if selection:
                    try:
                        rect = self._window_rect(selection[0])
                        if not self._validate_region(rect, bounds):
                            raise ValueError('Window is outside the selected monitor. Choose All monitors or move the window completely onto the screen.')
                        self.selected_window_hwnd, self.selected_window_title = selection
                        self._record_area_changed()
                        self.save_config()
                        if not self._recording:
                            self._set_record_state('Ready')
                        self._set_status(f'Window selected: {selection[1]} ({rect[2]} × {rect[3]}). Independent WGC capture requires the x64 build.')
                    except Exception as exc:
                        self._set_status(f'Cannot select window: {exc}', error=True)
                elif error:
                    self._set_status(f'Window selection failed: {error}', error=True)
                else:
                    self._set_status('Window selection cancelled.')

            def poll():
                if state['closed'] or self._closing:
                    return
                try:
                    point = wintypes.POINT()
                    if not user32.GetCursorPos(ctypes.byref(point)):
                        raise OSError('GetCursorPos failed')
                    hit = self._window_at_point(point.x, point.y, overlay.winfo_id())
                    if hit:
                        wx, wy, ww, wh = self._window_rect(hit[0])
                        # Clip only the highlight to the selected desktop bounds.
                        x1 = max(wx, left) - left
                        y1 = max(wy, top) - top
                        x2 = min(wx + ww, left + width) - left
                        y2 = min(wy + wh, top + height) - top
                        if x2 > x1 and y2 > y1:
                            canvas.coords(outline, x1, y1, x2, y2)
                            canvas.itemconfigure(outline, state='normal')
                            visible_name = hit[1][:85]
                            canvas.itemconfigure(name_text,
                                text=f'{visible_name}   ({ww} × {wh})')
                            state['hover'] = hit
                        else:
                            state['hover'] = None
                            canvas.itemconfigure(outline, state='hidden')
                    else:
                        state['hover'] = None
                        canvas.itemconfigure(outline, state='hidden')
                        canvas.itemconfigure(name_text, text='No selectable window here')
                except Exception as exc:
                    logging.debug('Window hover check failed: %s', exc)
                    state['hover'] = None
                    canvas.itemconfigure(outline, state='hidden')
                state['after'] = overlay.after(80, poll)

            def on_click(event):
                # Refresh the hit-test at click position in case of quick motion.
                try:
                    hit = self._window_at_point(left + event.x, top + event.y,
                                                overlay.winfo_id()) or state['hover']
                    if hit:
                        close(hit)
                    else:
                        canvas.itemconfigure(name_text,
                                             text='No application found — move mouse onto an HMI window')
                except Exception as exc:
                    logging.exception('Window selection click failed')
                    close(error=exc)

            canvas.bind('<ButtonRelease-1>', on_click)
            overlay.bind('<Escape>', lambda e: close())
            canvas.bind('<Escape>', lambda e: close())
            overlay.protocol('WM_DELETE_WINDOW', lambda: close())
            overlay.focus_force()
            canvas.focus_set()
            poll()
        except Exception as exc:
            logging.exception('Window selector failed')
            if overlay is not None:
                try:
                    overlay.destroy()
                except tk.TclError:
                    pass
            self._restore_after_record_selection()
            self._set_status(f'Window selector failed: {exc}', error=True)

    def show_record_window(self):
        if not self.selected_window_hwnd:
            self._set_status('Click Select Window first.')
            return
        try:
            x, y, w, h = self._window_rect(self.selected_window_hwnd)
            if self._recording:
                self._set_status('Show Window is disabled while recording.')
                return
            # Four thin floating borders instead of a filled panel obscuring the HMI.
            borders = []
            for bx, by, bw, bh in ((x, y, w, 5), (x, y+h-5, w, 5),
                                   (x, y, 5, h), (x+w-5, y, 5, h)):
                mark = tk.Toplevel(self.root)
                mark.overrideredirect(True)
                mark.attributes('-topmost', True)
                mark.configure(bg='#22dc70')
                mark.geometry(f'{bw}x{bh}{bx:+d}{by:+d}')
                borders.append(mark)
            for mark in borders:
                mark.after(1400, mark.destroy)
            self._set_status(f'Showing window outline: {self.selected_window_title} ({w} × {h})')
        except Exception as exc:
            self._set_status(f'Window no longer available: {exc}', error=True)

    def _record_area_bounds(self):
        """Use the selected physical monitor, or the complete virtual desktop."""
        if MSS_AVAILABLE:
            with mss.MSS() as grabber:
                monitors = grabber.monitors
                idx = 0
                if self.use_monitor_select_var.get():
                    match = next((m for m in self._monitors_cache
                                  if m['name'] == self.monitor_list_var.get()), None)
                    if match and 0 <= match['id'] < len(monitors):
                        idx = match['id']
                monitor = monitors[idx]
                return (int(monitor['left']), int(monitor['top']),
                        int(monitor['width']), int(monitor['height']))
        # Windows virtual desktop coordinates can start at negative X/Y.
        if os.name == 'nt':
            import ctypes
            u = ctypes.windll.user32
            if self.use_monitor_select_var.get():
                match = next((m for m in self._monitors_cache
                              if m['name'] == self.monitor_list_var.get()), None)
                if match and match.get('bbox'):
                    l, t, r, b = match['bbox']
                    return int(l), int(t), int(r-l), int(b-t)
            return (u.GetSystemMetrics(76), u.GetSystemMetrics(77),
                    u.GetSystemMetrics(78), u.GetSystemMetrics(79))
        return 0, 0, self.root.winfo_screenwidth(), self.root.winfo_screenheight()

    @staticmethod
    def _validate_region(region, bounds):
        if not isinstance(region, (list, tuple)) or len(region) != 4:
            return False
        try:
            x, y, w, h = map(int, region)
            left, top, bw, bh = map(int, bounds)
            return (w >= 32 and h >= 32 and x >= left and y >= top
                    and x + w <= left + bw and y + h <= top + bh)
        except (ValueError, TypeError):
            return False

    @staticmethod
    def _capture_region_pixels(region):
        x, y, w, h = region
        if MSS_AVAILABLE:
            with mss.MSS() as grabber:
                frame = grabber.grab({'left': x, 'top': y, 'width': w, 'height': h})
                return Image.frombytes('RGB', frame.size, frame.rgb)
        return ImageGrab.grab(bbox=(x, y, x + w, y + h), all_screens=True)

    def select_record_area(self):
        if self._recording or self._video_countdown_job is not None:
            self._set_status('Stop recording before changing the capture region.')
            return
        if self.record_area_mode_var.get() != 'Custom Region':
            return
        try:
            bounds = self._record_area_bounds()
        except Exception as exc:
            self._set_status(f'Cannot enumerate monitors: {exc}', error=True)
            return
        if self._begin_record_selection():
            self._selector_job = self.root.after(350, lambda: self._create_region_selector(bounds))

    def _create_region_selector(self, bounds):
        self._selector_job = None
        if self._closing or not getattr(self, '_selection_active', False):
            return
        left, top, width, height = bounds
        try:
            background = self._capture_region_pixels(bounds)
            overlay = tk.Toplevel(self.root)
            self._selector_overlay = overlay
            overlay.overrideredirect(True)
            overlay.attributes('-topmost', True)
            overlay.geometry(f'{width}x{height}{left:+d}{top:+d}')
            canvas = tk.Canvas(overlay, highlightthickness=0, cursor='crosshair')
            canvas.pack(fill='both', expand=True)
            preview = ImageTk.PhotoImage(background)
            canvas.create_image(0, 0, image=preview, anchor='nw')
            canvas.preview_image = preview
            canvas.create_rectangle(0,0,width,height,fill='#172335',stipple='gray25',outline='')
            canvas.create_text(width//2,24,text='Left-drag: Select · Right-click: Confirm · Esc: Cancel',
                               fill='white',font=('Segoe UI',13,'bold'))
            state = {'start': None, 'rect': None, 'coords': None}

            def down(e):
                x=max(0,min(width,e.x)); y=max(0,min(height,e.y))
                state['start']=(x,y)
                if state['rect'] is not None:
                    canvas.delete(state['rect'])
                state['rect']=canvas.create_rectangle(x,y,x,y,outline='#00aaff',width=3)
                state['coords']=None

            def move(e):
                if state['start'] is None:
                    return
                x=max(0,min(width,e.x)); y=max(0,min(height,e.y))
                canvas.coords(state['rect'],*state['start'],x,y)

            def up(e):
                if state['start'] is None:
                    return
                x0,y0=state['start']
                x1=max(0,min(width,e.x)); y1=max(0,min(height,e.y))
                x0,x1=sorted((x0,x1)); y0,y1=sorted((y0,y1))
                state['start']=None
                if x1-x0 >= 32 and y1-y0 >= 32:
                    state['coords']=(left+x0,top+y0,x1-x0,y1-y0)
                    canvas.coords(state['rect'],x0,y0,x1,y1)
                else:
                    state['coords']=None
                    self._set_status('Selection must be at least 32 × 32 pixels.')

            def finish(accept=False):
                # Canvas key events also reach their toplevel bindtag. Stop
                # propagation and guard repeat clicks before saving settings.
                if not self._selection_active:
                    return 'break'
                coords=state['coords'] if accept else None
                self._restore_after_record_selection()
                if coords:
                    self.record_region=coords
                    self._record_area_changed()
                    self.save_config()
                    self._set_status(f'Recording region selected: {coords}')
                elif accept:
                    self._set_status('Drag a rectangle first; selection not changed.')
                else:
                    self._set_status('Recording-area selection cancelled.')
                return 'break'

            overlay.protocol('WM_DELETE_WINDOW', lambda: finish(False))
            canvas.bind('<ButtonPress-1>',down)
            canvas.bind('<B1-Motion>',move)
            canvas.bind('<ButtonRelease-1>',up)
            overlay.bind('<Escape>',lambda e:finish(False))
            canvas.bind('<ButtonRelease-3>',lambda e:finish(True))
            overlay.bind('<Return>',lambda e:finish(True))
            overlay.bind('<Control-Return>',lambda e:finish(True))
            canvas.bind('<Escape>',lambda e:finish(False))
            canvas.bind('<Return>',lambda e:finish(True))
            overlay.focus_force()
            canvas.focus_set()
            # Right-click confirms. Enter remains an accessible fallback.
        except Exception as exc:
            logging.exception('Area selector failed')
            self._restore_after_record_selection()
            self._set_status(f'Area selector failed: {exc}', error=True)

    def show_record_area(self):
        if self._recording:
            self._set_status('Show Area is disabled during recording to avoid capturing the overlay.')
            return
        if not self.record_region:
            self._set_status('Select a recording region first.')
            return
        try:
            bounds=self._record_area_bounds()
            if not self._validate_region(self.record_region,bounds):
                self._set_status('Saved area is outside current monitor. Select Area again.',error=True)
                return
            x,y,w,h=self.record_region
            mark=tk.Toplevel(self.root)
            mark.overrideredirect(True)
            mark.attributes('-topmost',True)
            mark.attributes('-alpha',0.65)
            mark.geometry(f'{w}x{h}{x:+d}{y:+d}')
            frame=tk.Frame(mark,bg='#00a5ed',highlightbackground='#00a5ed',highlightthickness=4)
            frame.pack(fill='both',expand=True)
            tk.Label(frame,text=f'Recording region  {w} × {h}',bg='#00a5ed',fg='white',
                     font=('Segoe UI',13,'bold')).pack(pady=8)
            mark.after(1600,mark.destroy)
        except Exception as exc:
            self._set_status(f'Cannot display region: {exc}',error=True)

    # ---------- Recording related methods ----------
    def _record_options(self):
        return dict(save_as=self.save_as_var.get().strip(), save_dir=self.save_dir_var.get().strip(),
                    fps=max(1, min(60, int(self.rec_fps_var.get()))),
                    resolution=self.rec_res_var.get(),
                    monitor_enabled=bool(self.use_monitor_select_var.get()),
                    monitor_name=self.monitor_list_var.get(),
                    monitors=list(self._monitors_cache),
                    area_mode=self.record_area_mode_var.get(),
                    region=tuple(self.record_region) if self.record_region else None,
                    window_hwnd=self.selected_window_hwnd if self.record_area_mode_var.get() == 'Selected Window' else None)

    def check_recording(self):
        """Run a short encoder test; detailed results appear in app-data log."""
        self._set_status('Checking MP4 encoders...')
        threading.Thread(target=self._check_recording_worker, daemon=True).start()

    def _check_recording_worker(self):
        notes = [f'OpenCV import: {_cv2_available}', f'imageio import: {_imageio_available}',
                 f'FFmpeg executable: {ffmpeg_executable() or "not found"}']
        try:
            with tempfile.TemporaryDirectory() as tmp:
                dest = os.path.join(tmp, 'encoder_test.mp4')
                writer = RecordingWriter(dest, 5, (320, 240))
                notes.append('Selected encoder: ' + writer.backend)
                try:
                    writer.write(np.zeros((240, 320, 3), dtype=np.uint8))
                finally:
                    writer.close()
                notes.append('Output file bytes: ' + str(os.path.getsize(dest)))
        except Exception as exc:
            notes.append('FAILED: ' + str(exc))
        result = '\n'.join(notes)
        self._set_status(notes[-1] if 'FAILED:' in notes[-1] else 'Encoder check passed: ' + notes[-2])
        self._post_gui(messagebox.showinfo, 'Recording Compatibility', result)

    def start_recording(self):
        if getattr(self, '_selection_active', False):
            self._set_status('Finish or cancel the current selection first.')
            return
        if self._video_countdown_job is not None or self._recording:
            return
        try:
            delay = max(0, min(60, int(self.video_delay_seconds_var.get())))
        except (ValueError, tk.TclError):
            self._set_status("Recording delay must be between 0 and 60 seconds")
            return
        if not self.save_dir_var.get().strip():
            self._set_status("Save folder is required.")
            return
        self.start_rec_btn.config(state="disabled")
        self.stop_rec_btn.config(state="normal")
        self._set_record_state('Preparing', 'Preparing recording...')
        self._auto_record_minimized = bool(self.hide_during_capture_var.get()) and not self._manual_taskbar_hide
        if self._auto_record_minimized:
            self._minimize_to_taskbar()
        if delay == 0:
            self._start_recording_now()
        else:
            self._video_countdown_remaining = delay
            self._video_countdown_tick()

    def _video_countdown_tick(self):
        self._video_countdown_job = None
        if self._video_countdown_remaining <= 0:
            self._start_recording_now()
            return
        self._set_status(f"Video recording begins in {self._video_countdown_remaining} seconds (Stop to cancel)...")
        self._video_countdown_remaining -= 1
        self._video_countdown_job = self.root.after(1000, self._video_countdown_tick)

    def _start_recording_now(self):
        self._video_countdown_job = None
        try:
            opts = self._record_options()
        except (ValueError, tk.TclError) as exc:
            self._set_status(f'Invalid recording settings: {exc}')
            self._record_start_failed()
            return
        if opts['area_mode'] == 'Selected Window':
            try:
                from wgc_window_capture import validate_window_capture
                validate_window_capture(opts['window_hwnd'])
                selected_bounds = self._window_rect(opts['window_hwnd'])
                monitor_bounds = self._record_area_bounds()
                if not self._validate_region(selected_bounds, monitor_bounds):
                    raise ValueError('Selected window is outside the active monitor. Choose All monitors or reposition the HMI.')
            except Exception as exc:
                self._set_status(f'Select Window before recording: {exc}', error=True)
                self._record_start_failed()
                return
        if opts['area_mode'] == 'Custom Region':
            try:
                bounds = self._record_area_bounds()
                if not self._validate_region(opts['region'], bounds):
                    raise ValueError('Saved region invalid or outside selected monitor. Click Select Area.')
            except Exception as exc:
                self._set_status(str(exc), error=True)
                self._record_start_failed()
                return
        if not opts['save_dir']:
            self._set_status('Save folder is required.')
            self._record_start_failed()
            return
        if not (_cv2_available or _imageio_available):
            self._set_status('Recording unavailable: install imageio, imageio-ffmpeg or OpenCV.')
            self._record_start_failed()
            return
        try:
            target_dir = opts['save_dir']
            os.makedirs(target_dir, exist_ok=True)
            opts['base'] = opts['save_as'] or f"Recording_{datetime.now():%Y%m%d_%H%M%S}"
            opts['auto_name'] = not bool(opts['save_as'])
            if shutil.disk_usage(target_dir).free < MIN_FREE_DISK_BYTES:
                raise RuntimeError('Less than 2 GB available on recording drive')
            if opts['auto_name']:
                path = self._reserve_session_part(target_dir, opts['base'], 1)
            else:
                path = self._reserve_filename(target_dir, opts['base'], 'mp4', recording=True)
        except Exception as exc:
            self._set_status(f'Cannot create recording file: {exc}')
            self._record_start_failed()
            return
        opts['path'] = path
        opts['size'] = {'Native': None, '1080p': (1920, 1080), '1440p': (2560, 1440)}.get(opts['resolution'])
        with self._record_lock:
            if self._recording:
                try:
                    os.remove(path)
                except OSError:
                    pass
                return
            self._recording = True
            self._record_frames = 0
            self._record_start_monotonic = None  # starts after first verified screen frame
            self._record_part = 0
            self._record_segment_bytes = 0
            self._record_path = str(path)
            self._record_error = None
            self._record_success = False
            self._record_stop_event.clear()
        self._set_record_state('Preparing', 'Initializing recording encoder...')
        self.start_rec_btn.config(state='disabled')
        self.stop_rec_btn.config(state='normal')
        self._set_status('Starting recorder and checking encoder...')
        self._record_thread = threading.Thread(target=self._record_worker, args=(opts,), daemon=False)
        self._record_thread.start()

    def _record_start_failed(self):
        self._set_record_state('Error')
        self.start_rec_btn.config(state='normal')
        self.stop_rec_btn.config(state='disabled')
        if self._auto_record_minimized and not self._manual_taskbar_hide:
            self._minimize_pending = False
            self.root.deiconify()
        self._auto_record_minimized = False

    def stop_recording(self, wait=False):
        if self._video_countdown_job is not None:
            self.root.after_cancel(self._video_countdown_job)
            self._video_countdown_job = None
            self._video_countdown_remaining = 0
            self.start_rec_btn.config(state='normal')
            self.stop_rec_btn.config(state='disabled')
            self._set_record_state('Ready', 'Pending recording cancelled.')
            if self._auto_record_minimized and not self._manual_taskbar_hide:
                self._minimize_pending = False
                self.root.deiconify()
            self._auto_record_minimized = False
            return
        with self._record_lock:
            self._recording = False
        self._record_stop_event.set()
        self._set_record_state('Finalizing', 'Finalizing MP4 recording...')
        if wait and self._record_thread is not None:
            self._record_thread.join(timeout=10)
        elif not wait:
            self._set_status('Finalizing recording...')
        # Worker owns closing writer and resetting buttons, after MP4 finalized.

    @staticmethod
    def _reserve_session_part(directory, base, part):
        """Atomically reserve timestamped recording part, including the _01 suffix."""
        safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', base.strip()).rstrip('. ') or 'Recording'
        count = part
        while True:
            path = os.path.join(directory, f'{safe}_{count:02d}.mp4')
            try:
                fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o666)
                os.close(fd)
                return path
            except FileExistsError:
                count += 1

    def _next_record_path(self, opts):
        if opts['auto_name']:
            return self._reserve_session_part(opts['save_dir'], opts['base'], self._record_part + 1)
        return self._reserve_filename(opts['save_dir'], opts['base'], 'mp4', recording=True)

    def _record_worker(self, opts):
        path = opts['path']
        writer, grabber = None, None
        window_capture = None
        frames = 0
        part_frames = 0
        problem = None
        last_completed = None
        fps, size = opts['fps'], opts['size']
        finalized_paths = []
        timeline = None
        try:
            # For Native mode, determine the dimensions from the FIRST real frame.
            # Keep them constant across window moves, resize events and MP4 splits.
            with self._record_lock:
                self._record_part = 1
                self._record_path = path
            if opts.get('area_mode') == 'Selected Window':
                from wgc_window_capture import WindowCaptureSource
                window_capture = WindowCaptureSource(opts['window_hwnd'])
                window_capture.start()
            elif MSS_AVAILABLE:
                try:
                    grabber = mss.MSS()
                except Exception as exc:
                    logging.warning('mss unavailable: %s', exc)
            selected_idx, selected_bbox = 0, None
            if opts['monitor_enabled']:
                for m in opts['monitors']:
                    if m['name'] == opts['monitor_name']:
                        selected_idx, selected_bbox = m['id'], m.get('bbox')
                        break
            interval = 1.0 / fps
            last_preview = 0.0
            consecutive_errors = 0
            last_disk_check = 0.0
            while True:
                with self._record_lock:
                    if not self._recording:
                        break
                begun = time.monotonic()
                try:
                    if opts.get('area_mode') == 'Selected Window':
                        # Independent WGC HWND capture: never fall back to visible desktop
                        # cropping (which would accidentally record another application's UI).
                        img = window_capture.get_frame(timeout=6 if frames == 0 else 2)
                    elif opts.get('area_mode') == 'Custom Region':
                        x, y, w, h = opts['region']
                        if grabber is not None:
                            grab = grabber.grab({'left': x, 'top': y, 'width': w, 'height': h})
                            img = Image.frombytes('RGB', grab.size, grab.rgb)
                        else:
                            img = ImageGrab.grab(bbox=(x, y, x+w, y+h), all_screens=True)
                    elif grabber is not None:
                        monitors = grabber.monitors
                        idx = selected_idx if 0 < selected_idx < len(monitors) else 0
                        grab = grabber.grab(monitors[idx])
                        img = Image.frombytes('RGB', grab.size, grab.rgb)
                    else:
                        if selected_idx and selected_bbox:
                            img = ImageGrab.grab(bbox=selected_bbox)
                        else:
                            img = ImageGrab.grab(all_screens=True) if os.name == 'nt' else ImageGrab.grab()
                    if img.mode != 'RGB':
                        img = img.convert('RGB')
                    if size is None:
                        # YUV420p and many MP4 encoders require even dimensions.
                        size = ((img.width + 1) // 2 * 2, (img.height + 1) // 2 * 2)
                    if img.size != size:
                        if opts['resolution'] == 'Native':
                            # Preserve native pixels whenever the target window changes size.
                            # If enlarged, pad. If reduced, scale down only as required
                            # to maintain constant encoded frame dimensions.
                            if img.width > size[0] or img.height > size[1]:
                                img.thumbnail(size, Image.Resampling.LANCZOS)
                        else:
                            img.thumbnail(size, Image.Resampling.LANCZOS)
                        background = Image.new('RGB', size, (0, 0, 0))
                        background.paste(img, ((size[0] - img.width)//2, (size[1] - img.height)//2))
                        img = background
                    if writer is None:
                        writer = RecordingWriter(path, fps, size)
                        timeline = RecordingTimeline(writer, fps)
                    added = timeline.write(np.asarray(img), time.monotonic())
                    frames += added
                    part_frames += added
                    with self._record_lock:
                        self._record_frames = frames
                        if self._record_start_monotonic is None:
                            self._record_start_monotonic = time.monotonic()
                    if frames == added:
                        self._post_gui(self._set_record_state, 'Recording',
                                       f'Recording started: {Path(path).name} ({writer.backend})')
                    if self._preview_enabled.is_set() and (frames == 1 or time.monotonic() - last_preview >= 0.25):
                        try:
                            thumb = img.copy()
                            thumb.thumbnail((320, 180), Image.Resampling.BILINEAR)
                            with self._preview_lock:
                                self._preview_frame = thumb
                            last_preview = time.monotonic()
                        except Exception:
                            logging.exception('Video preview frame failed')
                    consecutive_errors = 0
                except Exception as exc:
                    consecutive_errors += 1
                    logging.exception('Recording frame failure')
                    if consecutive_errors >= 3:
                        raise RuntimeError('3 consecutive capture/encoder errors: ' + str(exc))

                current_time = time.monotonic()
                if current_time - last_disk_check >= 1.0:
                    last_disk_check = current_time
                    remaining = shutil.disk_usage(opts['save_dir']).free
                    if remaining < MIN_FREE_DISK_BYTES:
                        raise RuntimeError('Low disk space: less than 2 GB free. Recording stopped safely.')
                    try:
                        current_size = os.path.getsize(path)
                    except OSError:
                        current_size = 0
                    with self._record_lock:
                        self._record_segment_bytes = current_size
                    if current_size >= VIDEO_ROLLOVER_BYTES:
                        self._post_gui(self._set_record_state, 'Splitting',
                                       f'Finalizing video part {self._record_part:02d}...')
                        writer.close()
                        writer = None
                        final_size = os.path.getsize(path)
                        if final_size >= VIDEO_FILE_MAX_BYTES:
                            raise RuntimeError(f'Completed video exceeds 1 GB: {Path(path).name} ({final_size} bytes)')
                        if final_size < 1024:
                            raise RuntimeError('Video part is empty after finalizing')
                        finalized_paths.append(path)
                        last_completed = path
                        part_frames = 0  # Already finalized; do not count again on stop.
                        with self._record_lock:
                            still_recording = self._recording
                        if not still_recording:
                            break
                        path = self._next_record_path(opts)
                        part_frames = 0
                        writer = RecordingWriter(path, fps, size)
                        timeline.writer = writer
                        with self._record_lock:
                            self._record_part += 1
                            self._record_path = path
                            self._record_segment_bytes = 0
                        self._post_gui(self._set_record_state, 'Recording',
                                       f'Recording continuing: {Path(path).name}')
                delay = interval - (time.monotonic() - begun)
                if delay > 0:
                    self._record_stop_event.wait(delay)
            if frames == 0:
                raise RuntimeError('No screen frames captured')
        except Exception as exc:
            problem = str(exc)
            logging.exception('Recording stopped with error')
        finally:
            if window_capture is not None:
                try:
                    window_capture.close()
                except Exception:
                    logging.exception('Failed to close WGC window capture')
            if grabber is not None:
                try:
                    grabber.close()
                except Exception:
                    pass
            if writer is not None:
                try:
                    writer.close()
                except Exception as exc:
                    problem = problem or f'Failed to finalize MP4: {exc}'
            if part_frames > 0 and os.path.isfile(path):
                try:
                    final_size = os.path.getsize(path)
                    if final_size >= VIDEO_FILE_MAX_BYTES:
                        problem = problem or f'Completed file exceeds 1 GB: {Path(path).name}'
                    elif final_size < 1024:
                        problem = problem or 'MP4 file too small or invalid'
                    else:
                        finalized_paths.append(path)
                        last_completed = path
                except OSError as exc:
                    problem = problem or str(exc)
            elif not finalized_paths and not problem:
                problem = 'No finalized video segments'
            with self._record_lock:
                self._recording = False
                self._record_start_monotonic = None
            self._record_stop_event.set()
            with self._preview_lock:
                self._preview_frame = None
            self._record_error = problem
            self._record_success = not bool(problem)
            message = (f'Recording error: {problem}. {len(finalized_paths)} completed segment(s).' if problem else
                       f'Recording stopped. {len(finalized_paths)} video file(s) saved; last: {last_completed}')
            self._post_gui(self._record_end_status, message, bool(problem))
            self._post_gui(self._record_finished)

    def _record_end_status(self, message, has_error):
        self._set_record_state('Error' if has_error else 'Stopped', message)

    def _record_finished(self):
        if self._auto_record_minimized and not self._manual_taskbar_hide and not self._closing:
            self._minimize_pending = False
            self.root.deiconify()
        self._auto_record_minimized = False
        if not self._closing:
            self.start_rec_btn.config(state='normal')
            self.stop_rec_btn.config(state='disabled')

    # ---------- end recording methods ----------

def main():
    logdir = Path(os.getenv('APPDATA') or str(Path.home())) / 'screenshot_app'
    try:
        logdir.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(filename=str(logdir / 'capture_v10.log'), level=logging.INFO,
                            format='%(asctime)s %(levelname)s %(message)s')
    except Exception:
        logging.basicConfig(level=logging.INFO)
    root = tk.Tk()
    app = ScreenshotApp(root)
    # External updater needs positive GUI-startup acknowledgement for rollback.
    ack_path = os.environ.get('SMARTSCREEN_UPDATE_ACK')
    if ack_path:
        try:
            Path(ack_path).write_text('ready', encoding='utf-8')
        except Exception:
            logging.exception('Unable to acknowledge updated application startup')
    root.mainloop()


if __name__ == "__main__":
    main()
