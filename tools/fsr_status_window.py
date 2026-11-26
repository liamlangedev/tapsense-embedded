#!/usr/bin/env python3
"""Live Zone 1 FSR pressure level and ADC graph for the Nano."""
import argparse
import glob
import re
import time
import tkinter as tk

import serial

BAUD = 115200
LEVELS = (100, 350, 700)
SAMPLE = re.compile(rb"Pad1_A0:(\d+)")


def find_port():
    for pattern in ("/dev/ttyUSB*", "/dev/ttyACM*"):
        ports = sorted(glob.glob(pattern))
        if ports:
            return ports[0]


def pressure_level(value):
    if value < LEVELS[0]:
        return "NO PRESS", "#9CA3AF"
    if value < LEVELS[1]:
        return "LIGHT", "#38BDF8"
    if value < LEVELS[2]:
        return "MEDIUM", "#F59E0B"
    return "HARD", "#EF4444"


class StatusWindow:
    def __init__(self, root, port):
        self.root = root
        self.port = port
        self.ser = None
        self.buffer = b""
        self.last_try = 0.0
        self.points = []
        self.samples = 300
        self.current_value = None

        root.title("Zone 1 FSR — Live")
        root.configure(bg="#111827")
        root.geometry("700x440")
        root.resizable(True, True)
        tk.Label(root, text="ZONE 1 · A0", font=("sans-serif", 16, "bold"),
                 fg="#D1D5DB", bg="#111827").pack(pady=(14, 2))
        self.status = tk.Label(root, text="WAITING", font=("monospace", 22, "bold"),
                               fg="#9CA3AF", bg="#111827")
        self.status.pack(pady=2)
        self.canvas = tk.Canvas(root, bg="#0F131C", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=18, pady=12)
        self.canvas.bind("<Configure>", lambda _event: self.draw_graph())
        self.note = tk.Label(root, text="Connecting...", font=("monospace", 10),
                             fg="#6B7280", bg="#111827")
        self.note.pack(side="bottom", pady=(0, 12))
        root.after(50, self.tick)
        root.protocol("WM_DELETE_WINDOW", self.close)

    def connect(self):
        if time.monotonic() - self.last_try < 1:
            return
        self.last_try = time.monotonic()
        port = self.port or find_port()
        if not port:
            self.note.config(text="No serial port found — reconnecting...")
            return
        try:
            self.ser = serial.Serial(port, BAUD, timeout=0)
            self.buffer = b""
            self.note.config(text=f"{port} | ADC levels: {LEVELS[0]}, {LEVELS[1]}, {LEVELS[2]}")
        except (serial.SerialException, OSError) as error:
            self.ser = None
            self.note.config(text=f"{port}: {error} — reconnecting...")

    def tick(self):
        if self.ser is None or not self.ser.is_open:
            self.connect()
        else:
            try:
                self.buffer += self.ser.read(512)
                self.buffer = self.buffer[-2048:]
                while b"\n" in self.buffer:
                    line, self.buffer = self.buffer.split(b"\n", 1)
                    match = SAMPLE.search(line)
                    if match:
                        value = int(match.group(1))
                        self.current_value = value
                        self.points.append(value)
                        self.points = self.points[-self.samples:]
                        level, color = pressure_level(value)
                        self.status.config(text=level, fg=color)
                        self.draw_graph()
            except (serial.SerialException, OSError):
                self.ser.close()
                self.ser = None
                self.note.config(text="Serial disconnected — reconnecting...")
        self.root.after(40, self.tick)

    def draw_graph(self):
        canvas = self.canvas
        canvas.delete("all")
        width, height = canvas.winfo_width(), canvas.winfo_height()
        if width < 20 or height < 20:
            return
        left, right, top, bottom = 52, width - 16, 16, height - 34
        for value in (0, 512, 1023):
            y = bottom - value * (bottom - top) / 1023
            canvas.create_line(left, y, right, y, fill="#263244")
            canvas.create_text(left - 8, y, text=str(value), anchor="e",
                               fill="#9CA3AF", font=("monospace", 9))
        canvas.create_line(left, bottom, right, bottom, fill="#6B7280")
        canvas.create_text((left + right) / 2, height - 10,
                           text="Time → (last 6 seconds)", fill="#9CA3AF",
                           font=("monospace", 9))
        if len(self.points) > 1:
            coords = []
            for index, value in enumerate(self.points):
                x = left + index * (right - left) / (self.samples - 1)
                y = bottom - value * (bottom - top) / 1023
                coords.extend((x, y))
            canvas.create_line(*coords, fill="#38BDF8", width=2)
        for cutoff, color, label in zip(LEVELS, ("#38BDF8", "#F59E0B", "#EF4444"),
                                        ("LIGHT", "MEDIUM", "HARD")):
            y = bottom - cutoff * (bottom - top) / 1023
            canvas.create_line(left, y, right, y, fill=color, dash=(3, 4))
            canvas.create_text(right - 4, y - 3, text=label, anchor="se",
                               fill=color, font=("monospace", 8))
        if self.current_value is not None:
            canvas.create_text(right, top, text=f"{self.current_value} ADC",
                               anchor="ne", fill="#D1D5DB",
                               font=("monospace", 10, "bold"))

    def close(self):
        if self.ser and self.ser.is_open:
            self.ser.close()
        self.root.destroy()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", help="serial port (auto-detected by default)")
    parser.add_argument("--levels", type=int, nargs=3, metavar=("LIGHT", "MEDIUM", "HARD"),
                        default=LEVELS,
                        help="increasing ADC cutoffs for light, medium, and hard press")
    args = parser.parse_args()
    LEVELS = tuple(args.levels)
    if not 0 <= LEVELS[0] < LEVELS[1] < LEVELS[2] <= 1023:
        parser.error("levels must be increasing ADC values between 0 and 1023")
    window = tk.Tk()
    StatusWindow(window, args.port)
    window.mainloop()
