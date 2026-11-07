"""Nonmodal embedded player, native file drops and a draggable trim timeline."""
import os
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from PIL import ImageTk
from video_editing import Clip, probe_video, export_video
from video_playback import PreviewPlayer
from video_timeline import VideoTimeline


class VideoEditor:
    def __init__(self, parent, executable):
        self.executable = executable
        self.window = tk.Toplevel(parent)
        self.window.title('Edit Video — Player, Trim and Join')
        self.window.geometry('900x740')
        self.window.minsize(760, 680)
        self.window.resizable(True, True)
        # Independent toplevel: no modal grab/transient owner hiding or blocking
        # the editor when switching to another Windows application.
        self.player = PreviewPlayer(executable)
        self.player_revision = 0
        self.playing = False
        self._seek_job = None
        self._resize_job = None
        self._display_image = None
        self._selected_index = None
        self.clips = []
        self.infos = []
        self.busy = False
        self.closing = False
        self.events = queue.Queue()
        self.cancel = threading.Event()
        self.controls = []
        body = ttk.Frame(self.window, padding=12)
        body.pack(fill='both', expand=True)
        self.drop_label = ttk.Label(body, text='Drop video files here or use Add videos. Originals stay unchanged.')
        self.drop_label.pack(anchor='w')
        self.listbox = tk.Listbox(body, height=5, exportselection=False)
        self.listbox.pack(fill='x', pady=6)
        self.listbox.bind('<<ListboxSelect>>', self.select)
        row = ttk.Frame(body); row.pack(fill='x')
        for title, command in [('Add videos', self.add), ('Remove', self.remove),
                               ('Move up', lambda: self.move(-1)), ('Move down', lambda: self.move(1))]:
            self.button(row, title, command).pack(side='left', padx=3)
        preview_holder = ttk.Frame(body, height=150)
        preview_holder.pack(fill='both', expand=True, pady=8)
        preview_holder.pack_propagate(False)
        self.preview = ttk.Label(preview_holder, text='Select a video to preview a frame.', anchor='center')
        self.preview.pack(fill='both', expand=True)
        self.preview.bind('<Configure>', self.resize_preview)
        self.position = tk.DoubleVar(value=0)
        self.timeline = VideoTimeline(body, self.scrub, self.select_range)
        self.timeline.pack(fill='x')
        self.timeline.enabled = False
        self.clock = tk.StringVar(value='0.000 / 0.000 sec')
        ttk.Label(body, textvariable=self.clock).pack(anchor='w')
        row = ttk.Frame(body); row.pack(fill='x', pady=4)
        self.play_button = self.button(row, 'Play selection', self.toggle_play)
        self.play_button.pack(side='left')
        self.button(row, '◀ Frame', lambda: self.step_frame(-1)).pack(side='left', padx=3)
        self.button(row, 'Frame ▶', lambda: self.step_frame(1)).pack(side='left', padx=3)
        ttk.Label(row, text='Volume').pack(side='left', padx=(10, 3))
        self.volume = tk.DoubleVar(value=1)
        self.volume_control = ttk.Scale(row, from_=0, to=1, variable=self.volume,
                                        command=lambda value: self.change_volume())
        self.volume_control.pack(side='left', fill='x', expand=True)
        self.controls.append(self.volume_control)
        self.button(row, 'Maximize / Restore', self.toggle_maximize).pack(side='right')
        row = ttk.Frame(body); row.pack(fill='x', pady=4)
        self.start = tk.StringVar(value='0'); self.end = tk.StringVar(value='0')
        self.tail = tk.StringVar(value='5')
        for label, variable in [('Keep from (sec)', self.start), ('to (sec)', self.end)]:
            ttk.Label(row, text=label).pack(side='left', padx=(0, 5))
            entry = ttk.Entry(row, textvariable=variable, width=10); entry.pack(side='left', padx=(0, 10))
            self.controls.append(entry)
        self.button(row, 'Apply range', self.apply_range).pack(side='left')
        row = ttk.Frame(body); row.pack(fill='x', pady=4)
        self.button(row, 'Remove last', self.remove_tail).pack(side='left')
        entry = ttk.Entry(row, textvariable=self.tail, width=6); entry.pack(side='left', padx=5)
        self.controls.append(entry)
        ttk.Label(row, text='seconds from the selected original (default 5)').pack(side='left')
        row = ttk.Frame(body); row.pack(fill='x', pady=6)
        ttk.Label(row, text='Output size').pack(side='left')
        self.resolution = tk.StringVar(value='Match first video')
        combo = ttk.Combobox(row, textvariable=self.resolution, state='readonly', width=20,
                             values=['Match first video', '720p', '1080p', '1440p'])
        combo.pack(side='left', padx=8); self.controls.append(combo)
        self.fps = tk.StringVar(value='30')
        ttk.Label(row, text='FPS').pack(side='left')
        spin = ttk.Spinbox(row, from_=1, to=60, textvariable=self.fps, width=6)
        spin.pack(side='left', padx=8); self.controls.append(spin)
        row = ttk.Frame(body); row.pack(fill='x')
        self.button(row, 'Export new MP4…', self.export).pack(side='left')
        self.cancel_btn = ttk.Button(row, text='Cancel operation', command=self.cancel.set, state='disabled')
        self.cancel_btn.pack(side='left', padx=8)
        self.status = tk.StringVar(value='Trim one video, or add several to join in list order. Audio is retained.')
        ttk.Label(body, textvariable=self.status, wraplength=850).pack(fill='x', pady=8)
        self.window.protocol('WM_DELETE_WINDOW', self.close)
        self.enable_drop()
        self.window.after(20, self.poll)

    def button(self, parent, title, command):
        button = ttk.Button(parent, text=title, command=command)
        self.controls.append(button)
        return button

    def enable_drop(self):
        try:
            from tkinterdnd2 import DND_FILES, TkinterDnD
            TkinterDnD._require(self.window)
            for widget in (self.window, self.listbox, self.preview, self.drop_label):
                widget.drop_target_register(DND_FILES)
                widget.dnd_bind('<<Drop>>', self.drop_files)
        except (ImportError, tk.TclError, RuntimeError) as exc:
            self.drop_label.configure(text='File drop unavailable; use Add videos. Rebuild with tkinterdnd2.')
            self.status.set(f'Drag-and-drop could not initialize: {exc}')

    def drop_files(self, event):
        if self.busy or self.closing:
            self.status.set('Finish or cancel the current operation before adding files.')
            return 'refuse_drop'
        try:
            paths = self.window.tk.splitlist(event.data)
            if not paths or not all(Path(path).is_file() for path in paths):
                raise ValueError('Drop local video files, not folders.')
            self.add_paths(paths)
            return 'copy'
        except (ValueError, tk.TclError) as exc:
            self.status.set(str(exc))
            return 'refuse_drop'

    def toggle_maximize(self):
        try:
            self.window.state('normal' if self.window.state() == 'zoomed' else 'zoomed')
        except tk.TclError:
            try:
                self.window.attributes('-zoomed', not self.window.attributes('-zoomed'))
            except tk.TclError:
                self.status.set('Use your window manager maximize button.')

    def index(self):
        selection = self.listbox.curselection()
        if not selection:
            raise ValueError('Select a video in the list first.')
        return selection[0]

    def refresh(self, selected=0, preview=True):
        self.listbox.delete(0, 'end')
        for clip in self.clips:
            self.listbox.insert('end', f'{Path(clip.path).name}   |   keep {clip.start:.3f} – {clip.end:.3f} sec')
        if self.clips:
            self.listbox.selection_set(min(selected, len(self.clips)-1))
            self.select(preview=preview)
        else:
            self._selected_index = None
            self.pause_player()
            self.player_revision = self.player.request(path=None, position=0, playing=False)
            self._display_image = None
            self.timeline.enabled = False
            self.timeline.set_values(1, 0, 1, 0)
            self.clock.set('0.000 / 0.000 sec')
            self.preview.configure(image='', text='Add a video to begin.')
            self.preview.image = None
            self.start.set('0'); self.end.set('0')

    def select(self, event=None, preview=True):
        if self.busy or not self.clips:
            return
        try:
            i = self.index()
            if event is not None and i == self._selected_index:
                return
            if i != self._selected_index:
                self._display_image = None
                self.preview.configure(image='', text='Loading preview…')
                self.preview.image = None
            self._selected_index = i
            self.timeline.enabled = True
            clip = self.clips[i]
            self.start.set(f'{clip.start:.3f}'); self.end.set(f'{clip.end:.3f}')
            self.pause_player()
            self.position.set(clip.start)
            self.update_timeline()
            if preview:
                self.preview_at_position()
        except ValueError as exc:
            self.status.set(str(exc))

    def task(self, work, done):
        if self.busy:
            return
        self.pause_player()
        self.busy = True; self.cancel.clear()
        self.timeline.enabled = False
        for control in self.controls:
            control.state(['disabled'])
        self.listbox.configure(state='disabled')
        self.cancel_btn.state(['!disabled'])
        def run():
            try:
                self.events.put(('done', (done, work())))
            except Exception as exc:
                self.events.put(('error', str(exc)))
        threading.Thread(target=run, daemon=True).start()

    def poll(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == 'progress':
                    self.status.set(value)
                    continue
                self.busy = False
                self.timeline.enabled = bool(self.clips)
                for control in self.controls:
                    control.state(['!disabled'])
                self.listbox.configure(state='normal')
                self.cancel_btn.state(['disabled'])
                if not self.closing:
                    if kind == 'done':
                        callback, result = value
                        try:
                            callback(result)
                        except Exception as exc:
                            self.status.set(f'Operation completed but the display could not update: {exc}')
                    else:
                        self.status.set(value)
        except queue.Empty:
            pass
        try:
            revision, kind, payload = self.player.frames.get_nowait()
            if revision == self.player_revision and not self.closing:
                if kind == 'frame':
                    image, position = payload
                    self.position.set(position)
                    self._display_image = image
                    self.render_image()
                    self.update_timeline()
                elif kind == 'ended':
                    self.playing = False
                    self.play_button.configure(text='Play selection')
                    self.status.set('Reached the selected end. Original file is unchanged.')
                else:
                    self.playing = False
                    self.play_button.configure(text='Play selection')
                    self.status.set(payload)
        except queue.Empty:
            pass
        # A bounded video queue may replace the final "ended" notification with
        # its paused boundary frame while the application is unfocused. Reconcile
        # transport state independently so the Pause button cannot get stuck.
        state = self.player.snapshot()
        if self.playing and not state['playing']:
            self.playing = False
            self.play_button.configure(text='Play selection')
        if self.closing and not self.busy and not self.player.thread.is_alive():
            self.window.destroy()
            return
        self.window.after(20, self.poll)

    def add(self):
        paths = filedialog.askopenfilenames(parent=self.window, title='Add videos in join order',
                                           filetypes=[('Video files', '*.mp4 *.mkv *.avi *.mov *.wmv'), ('All files', '*.*')])
        if not paths:
            return
        self.add_paths(paths)

    def add_paths(self, paths):
        if self.busy or self.closing:
            return
        paths = tuple(paths)
        if not paths:
            return
        def work():
            return [(str(Path(p).resolve()), probe_video(self.executable, p, self.cancel)) for p in paths]
        def done(items):
            first = len(self.clips)
            for path, info in items:
                self.clips.append(Clip(path, 0, info.duration)); self.infos.append(info)
            if first == 0:
                self.fps.set(str(min(60, max(1, round(items[0][1].fps)))))
            self.status.set('Select a clip and preview its start/end before exporting.')
            self.refresh(first)
        self.status.set('Reading video information…')
        self.task(work, done)

    def update_timeline(self):
        if not self.clips:
            return
        try:
            i = self.index(); clip = self.clips[i]; info = self.infos[i]
            self.timeline.set_values(info.duration, clip.start, clip.end, self.position.get(), info.fps)
            self.clock.set(f'{self.position.get():.3f} / {info.duration:.3f} sec   |   Keep {clip.start:.3f} – {clip.end:.3f}')
        except ValueError:
            pass

    def preview_at_position(self):
        if self.busy or not self.clips or self.closing:
            return
        try:
            i = self.index(); info = self.infos[i]
            position = min(max(0, self.position.get()), max(0, info.duration - 1/max(1, info.fps)))
            self.pause_player()
            self.player_revision = self.player.request(path=self.clips[i].path, position=position,
                                                       end=self.clips[i].end, playing=False)
        except (ValueError, tk.TclError) as exc:
            self.status.set(str(exc))

    def pause_player(self):
        self.playing = False
        self.play_button.configure(text='Play selection')
        self.player_revision = self.player.request(playing=False, position=self.position.get())

    def toggle_play(self):
        if self.busy or not self.clips:
            return
        if self.playing:
            self.pause_player()
            return
        if not self.apply_range(preview=False):
            return
        i = self.index(); clip = self.clips[i]
        position = self.position.get()
        if not clip.start <= position < clip.end - 1/max(1, self.infos[i].fps):
            position = clip.start
        self.playing = True
        self.play_button.configure(text='Pause')
        width = max(160, min(1280, self.preview.winfo_width())) // 8 * 8
        self.player_revision = self.player.request(path=clip.path, position=position, end=clip.end,
                                    playing=True, volume=self.volume.get(), width=width)
        self.status.set('Playing selected range inside SmartScreen.')

    def change_volume(self):
        self.player_revision = self.player.request(volume=self.volume.get())

    def step_frame(self, direction):
        if not self.clips or self.busy:
            return
        self.scrub(self.position.get() + direction / max(1, self.infos[self.index()].fps))

    def scrub(self, position):
        if self.busy or not self.clips:
            return
        self.pause_player()
        info = self.infos[self.index()]
        self.position.set(max(0, min(position, max(0, info.duration-1/max(1, info.fps)))))
        self.update_timeline()
        if self._seek_job is not None:
            self.window.after_cancel(self._seek_job)
        self._seek_job = self.window.after(70, self.finish_scrub)

    def finish_scrub(self):
        self._seek_job = None
        self.preview_at_position()

    def select_range(self, start, end, position):
        if self.busy:
            return
        i = self.index()
        self.clips[i] = Clip(self.clips[i].path, start, end)
        self.start.set(f'{start:.6f}'); self.end.set(f'{end:.6f}')
        self.listbox.delete(i)
        self.listbox.insert(i, f'{Path(self.clips[i].path).name}   |   keep {start:.3f} – {end:.3f} sec')
        self.listbox.selection_clear(0, 'end')
        self.listbox.selection_set(i)
        self.scrub(position)

    def resize_preview(self, event=None):
        if self._resize_job is not None:
            self.window.after_cancel(self._resize_job)
        self._resize_job = self.window.after(60, self.finish_resize)

    def finish_resize(self):
        self._resize_job = None
        if not self.closing:
            if self.playing:
                width = max(160, min(1280, self.preview.winfo_width())) // 8 * 8
                self.player_revision = self.player.request(width=width)
            self.render_image()

    def render_image(self):
        if self._display_image is None:
            return
        image = self._display_image.copy()
        image.thumbnail((max(1, self.preview.winfo_width()), max(1, self.preview.winfo_height())))
        photo = ImageTk.PhotoImage(image)
        self.preview.configure(image=photo, text='')
        self.preview.image = photo

    def apply_range(self, preview=True):
        try:
            i = self.index()
            start, end = float(self.start.get()), float(self.end.get())
            if not 0 <= start < end <= self.infos[i].duration:
                raise ValueError('Enter 0 ≤ start < end ≤ original duration.')
            position = self.position.get()
            self.clips[i] = Clip(self.clips[i].path, start, end)
            self.refresh(i, preview=False)
            self.position.set(max(start, min(position, end)))
            self.update_timeline()
            if preview:
                self.preview_at_position()
            return True
        except (ValueError, tk.TclError) as exc:
            self.status.set(str(exc)); return False

    def remove_tail(self):
        try:
            i = self.index()
            seconds = float(self.tail.get())
            if not 0 < seconds < self.infos[i].duration - float(self.start.get()):
                raise ValueError('Choose a positive removal duration shorter than the remaining clip.')
            self.end.set(f'{self.infos[i].duration - seconds:.6f}')
            self.apply_range()
        except (ValueError, tk.TclError) as exc:
            self.status.set(str(exc))

    def remove(self):
        try:
            i = self.index()
            self.clips.pop(i); self.infos.pop(i)
            self.refresh(max(0, i-1))
        except ValueError as exc:
            self.status.set(str(exc))

    def move(self, step):
        try:
            i = self.index(); j = i + step
            if 0 <= j < len(self.clips):
                self.clips[i], self.clips[j] = self.clips[j], self.clips[i]
                self.infos[i], self.infos[j] = self.infos[j], self.infos[i]
                self.refresh(j)
        except ValueError as exc:
            self.status.set(str(exc))

    def export(self):
        if not self.clips:
            self.status.set('Add at least one video.'); return
        # Commit typed values without launching another preview worker.
        if not self.apply_range(preview=False):
            return
        try:
            fps = float(self.fps.get())
            sizes = {'720p': (1280, 720), '1080p': (1920, 1080), '1440p': (2560, 1440)}
            first = self.infos[0]
            size = sizes.get(self.resolution.get(), ((first.width+1)//2*2, (first.height+1)//2*2))
        except (ValueError, tk.TclError) as exc:
            self.status.set(str(exc)); return
        output = filedialog.asksaveasfilename(parent=self.window, title='Save new MP4 (choose a new name)',
                                             defaultextension='.mp4', filetypes=[('MP4 video', '*.mp4')])
        if not output:
            return
        clips = list(self.clips)
        self.status.set('Exporting… Originals remain unchanged. Extra disk space is needed for temporary clips.')
        def done(path):
            self.status.set('Saved: ' + path)
            messagebox.showinfo('Video exported', 'Saved new MP4:\n' + path + '\n\nOriginal videos are unchanged.', parent=self.window)
        self.task(lambda: export_video(self.executable, clips, output, size, fps, self.cancel,
                                      lambda text: self.events.put(('progress', text))), done)

    def close(self):
        if self.busy:
            if not messagebox.askyesno('Cancel editing?', 'Cancel the current operation and close the editor?', parent=self.window):
                return
            self.cancel.set()
        self.closing = True
        for job in (self._seek_job, self._resize_job):
            if job is not None:
                self.window.after_cancel(job)
        self.player.close()
