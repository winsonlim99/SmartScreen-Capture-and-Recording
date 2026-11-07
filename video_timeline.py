"""Draggable playhead and distinct start/end selection handles in source seconds."""
import tkinter as tk


class VideoTimeline(tk.Canvas):
    def __init__(self, parent, on_seek, on_range):
        super().__init__(parent, height=86, background='#172335', highlightthickness=0, takefocus=True)
        self.on_seek, self.on_range = on_seek, on_range
        self.duration = 1.0
        self.start, self.end, self.position = 0.0, 1.0, 0.0
        self.step = 0.01
        self.drag = None
        self.enabled = True
        self.bind('<Configure>', lambda e: self.redraw())
        self.bind('<ButtonPress-1>', self.down)
        self.bind('<B1-Motion>', self.motion)
        self.bind('<ButtonRelease-1>', self.up)

    def x(self, seconds):
        return 20 + seconds / max(self.duration, 0.001) * max(1, self.winfo_width() - 40)

    def seconds(self, x):
        return max(0, min(self.duration, (x - 20) / max(1, self.winfo_width() - 40) * self.duration))

    def set_values(self, duration, start, end, position, fps=30):
        self.duration, self.start, self.end, self.position = duration, start, end, position
        self.step = min(1 / max(1, fps), duration)
        self.redraw()

    def redraw(self):
        self.delete('all')
        self.create_rectangle(20, 29, max(21, self.winfo_width()-20), 54, fill='#43536b', outline='')
        self.create_rectangle(self.x(self.start), 29, self.x(self.end), 54, fill='#246be8', outline='')
        for seconds, label in ((self.start, 'START'), (self.end, 'END')):
            x = self.x(seconds)
            self.create_line(x, 22, x, 59, fill='#4ce1ba', width=4)
            self.create_polygon(x-7, 18, x+7, 18, x, 27, fill='#4ce1ba')
            self.create_text(x, 8, text=label, fill='white', font=('Segoe UI', 8))
        x = self.x(self.position)
        self.create_line(x, 31, x, 64, fill='#ffcd59', width=2)
        self.create_polygon(x-6, 65, x+6, 65, x, 57, fill='#ffcd59')
        self.create_text(20, 76, text='0:00', fill='white', anchor='w')
        self.create_text(self.winfo_width()-20, 76, text=f'{self.duration:.2f}s', fill='white', anchor='e')

    def down(self, event):
        if not self.enabled:
            return
        # Handles live above the bar; playhead lives below. This separates all
        # three targets even when a selected boundary matches the playhead.
        if event.y <= 29:
            self.drag = 'start' if abs(event.x-self.x(self.start)) <= abs(event.x-self.x(self.end)) else 'end'
        else:
            self.drag = 'position'
        self.motion(event)

    def motion(self, event):
        if not self.enabled or self.drag is None:
            return
        value = self.seconds(event.x)
        value = min(self.duration, round(value / max(self.step, 1e-9)) * self.step)
        if self.drag == 'start':
            self.start = max(0, min(value, self.end-self.step))
            self.position = self.start
            self.on_range(self.start, self.end, self.position)
        elif self.drag == 'end':
            self.end = min(self.duration, max(value, self.start+self.step))
            self.position = max(self.start, self.end-self.step)
            self.on_range(self.start, self.end, self.position)
        else:
            self.position = max(0, min(value, max(0, self.duration-self.step)))
            self.on_seek(self.position)
        self.redraw()

    def up(self, event):
        self.motion(event)
        self.drag = None
