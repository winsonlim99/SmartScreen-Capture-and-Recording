"""Tk editor with seekable frame preview and background, cancellable export."""
import os
from pathlib import Path
import queue
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from PIL import ImageTk
from video_editing import Clip, EditCancelled, probe_video, preview_frame, export_video


class VideoEditor:
    def __init__(self, parent, executable):
        self.executable = executable
        self.window = tk.Toplevel(parent)
        self.window.title('Edit Video — Trim and Join')
        self.window.geometry('900x740')
        self.window.minsize(760, 680)
        self.window.transient(parent)
        self.window.grab_set()
        self.clips = []
        self.infos = []
        self.busy = False
        self.closing = False
        self.events = queue.Queue()
        self.cancel = threading.Event()
        self.controls = []
        body = ttk.Frame(self.window, padding=12)
        body.pack(fill='both', expand=True)
        ttk.Label(body, text='Add videos, set the section to keep, and export a new MP4. Originals stay unchanged.').pack(anchor='w')
        self.listbox = tk.Listbox(body, height=5, exportselection=False)
        self.listbox.pack(fill='x', pady=6)
        self.listbox.bind('<<ListboxSelect>>', self.select)
        row = ttk.Frame(body); row.pack(fill='x')
        for title, command in [('Add videos', self.add), ('Remove', self.remove),
                               ('Move up', lambda: self.move(-1)), ('Move down', lambda: self.move(1))]:
            self.button(row, title, command).pack(side='left', padx=3)
        preview_holder = ttk.Frame(body, height=240)
        preview_holder.pack(fill='both', expand=True, pady=8)
        preview_holder.pack_propagate(False)
        self.preview = ttk.Label(preview_holder, text='Select a video to preview a frame.', anchor='center')
        self.preview.pack(fill='both', expand=True)
        self.position = tk.DoubleVar(value=0)
        self.seek = ttk.Scale(body, variable=self.position, from_=0, to=1)
        self.seek.pack(fill='x')
        self.controls.append(self.seek)
        row = ttk.Frame(body); row.pack(fill='x', pady=4)
        self.button(row, 'Preview frame at slider', self.preview_at_position).pack(side='left')
        self.button(row, 'Play original in player', self.play_original).pack(side='left', padx=5)
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
        self.window.after(80, self.poll)

    def button(self, parent, title, command):
        button = ttk.Button(parent, text=title, command=command)
        self.controls.append(button)
        return button

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
            self.preview.configure(image='', text='Add a video to begin.')
            self.preview.image = None
            self.start.set('0'); self.end.set('0')

    def select(self, event=None, preview=True):
        if self.busy or not self.clips:
            return
        try:
            i = self.index()
            clip = self.clips[i]
            self.start.set(f'{clip.start:.3f}'); self.end.set(f'{clip.end:.3f}')
            self.seek.configure(to=max(0, self.infos[i].duration - 0.1))
            self.position.set(clip.start)
            if preview:
                self.preview_at_position()
        except ValueError as exc:
            self.status.set(str(exc))

    def task(self, work, done):
        if self.busy:
            return
        self.busy = True; self.cancel.clear()
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
                for control in self.controls:
                    control.state(['!disabled'])
                self.listbox.configure(state='normal')
                self.cancel_btn.state(['disabled'])
                if not self.closing:
                    if kind == 'done':
                        callback, result = value
                        callback(result)
                    else:
                        self.status.set(value)
        except queue.Empty:
            pass
        if self.closing and not self.busy:
            self.window.destroy()
            return
        self.window.after(80, self.poll)

    def add(self):
        paths = filedialog.askopenfilenames(parent=self.window, title='Add videos in join order',
                                           filetypes=[('Video files', '*.mp4 *.mkv *.avi *.mov *.wmv'), ('All files', '*.*')])
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

    def preview_at_position(self):
        if self.busy:
            return
        try:
            clip = self.clips[self.index()]
            position = min(max(0, self.position.get()), max(0, self.infos[self.index()].duration - 0.1))
        except (ValueError, IndexError, tk.TclError) as exc:
            self.status.set(str(exc)); return
        def done(image):
            image.thumbnail((640, 240))
            photo = ImageTk.PhotoImage(image)
            self.preview.configure(image=photo, text='')
            self.preview.image = photo
            self.status.set(f'Preview position: {position:.3f} sec. Export keeps the applied range.')
        self.task(lambda: preview_frame(self.executable, clip.path, position, self.cancel), done)

    def play_original(self):
        try:
            path = self.clips[self.index()].path
            if os.name == 'nt':
                os.startfile(path)
            else:
                subprocess.Popen(['xdg-open', path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except (ValueError, OSError) as exc:
            self.status.set(str(exc))

    def apply_range(self, preview=True):
        try:
            i = self.index()
            start, end = float(self.start.get()), float(self.end.get())
            if not 0 <= start < end <= self.infos[i].duration:
                raise ValueError('Enter 0 ≤ start < end ≤ original duration.')
            self.clips[i] = Clip(self.clips[i].path, start, end)
            self.refresh(i, preview=preview)
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
