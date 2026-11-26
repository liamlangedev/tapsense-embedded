#!/usr/bin/env python3
"""Plot recent Nano readings from fsr_raw.log; updates while the log grows."""
import re
import tkinter as tk

LOG = "/tmp/fsr_raw.log"
SAMPLE = re.compile(r"(?:Pad1_A0:)?(\d+)")

class Plot:
    def __init__(self, root):
        self.root = root
        self.values = []
        root.title("FSR A0 · ON/OFF")
        root.configure(bg="#111827")
        root.geometry("720x380")
        self.title = tk.Label(root, text="A0 · NO PRESS", fg="#9CA3AF", bg="#111827", font=("monospace", 22, "bold"))
        self.title.pack(pady=8)
        self.canvas = tk.Canvas(root, bg="#0F131C", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=14, pady=8)
        self.note = tk.Label(root, text=LOG, fg="#6B7280", bg="#111827", font=("monospace", 10))
        self.note.pack(pady=8)
        self.canvas.bind("<Configure>", lambda _e: self.draw())
        self.poll()

    def poll(self):
        try:
            with open(LOG) as f:
                vals = [int(m.group(1)) for line in f for m in [SAMPLE.search(line)] if m]
            self.values = vals[-300:]
            if self.values:
                v = self.values[-1]
                on = v >= 700
                self.title.config(text=f"A0 · {'ON' if on else 'OFF'} · {v}", fg="#22C55E" if on else "#9CA3AF")
                self.draw()
        except OSError as e:
            self.note.config(text=str(e))
        self.root.after(250, self.poll)

    def draw(self):
        c = self.canvas
        c.delete("all")
        w, h = c.winfo_width(), c.winfo_height()
        if w < 50 or h < 50: return
        left, right, top, bottom = 48, w - 12, 18, h - 28
        for v in (0, 350, 700, 1023):
            y = bottom - v * (bottom - top) / 1023
            c.create_line(left, y, right, y, fill="#263244")
            c.create_text(left - 5, y, text=str(v), anchor="e", fill="#9CA3AF", font=("monospace", 8))
        if len(self.values) > 1:
            pts = []
            for i, v in enumerate(self.values):
                pts.extend((left + i * (right - left) / 299, bottom - v * (bottom - top) / 1023))
            c.create_line(*pts, fill="#38BDF8", width=2)

root = tk.Tk()
Plot(root)
root.mainloop()
