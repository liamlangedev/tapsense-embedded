#!/usr/bin/env python3
"""Live A0 ON/OFF plot from Arduino Nano serial output."""
import argparse, glob, re, time, tkinter as tk

THRESHOLD = 150
SAMPLE = re.compile(r"Pad1_A0:(\d+)")
import serial

BAUD = 115200

def find_port():
    for p in ('/dev/ttyUSB*', '/dev/ttyACM*'):
        hits = sorted(glob.glob(p))
        if hits: return hits[0]
    return None

class App:
    def __init__(self, root, port_override=None):
        self.root, self.port_override = root, port_override
        self.ser = None
        self.buf = b''
        self.last_try = 0.0
        self.samples = []
        root.title('FSR A0 ON/OFF')
        root.configure(bg='#111827')
        root.geometry('760x420')
        self.label = tk.Label(root, text='WAITING', font=('monospace', 28, 'bold'), fg='#9CA3AF', bg='#111827')
        self.label.pack(pady=8)
        self.canvas = tk.Canvas(root, bg='#0F131C', highlightthickness=0)
        self.canvas.pack(fill='both', expand=True, padx=16, pady=12)
        self.note = tk.Label(root, text='Waiting for Nano serial data', fg='#9CA3AF', bg='#111827')
        self.note.pack(pady=8)
        self.canvas.bind('<Configure>', lambda _e: self.draw())
        root.after(50, self.tick)

    def try_connect(self):
        if time.monotonic() - self.last_try < 1: return
        self.last_try = time.monotonic()
        ports = [self.port_override] if self.port_override else sorted(glob.glob('/dev/ttyUSB*') + glob.glob('/dev/ttyACM*'))
        for port in ports:
            try:
                self.ser = serial.Serial(port, BAUD, timeout=0)
                self.buf = b''
                self.note.config(text=f'{port} · A0 threshold {THRESHOLD}')
                return
            except (serial.SerialException, OSError):
                pass
        self.label.config(text='WAITING', fg='#9CA3AF')
        self.note.config(text='No readable Nano serial port; reconnecting...')

    def tick(self):
        if self.ser is None or not self.ser.is_open:
            self.try_connect()
        else:
            try:
                self.buf = (self.buf + self.ser.read(512))[-2048:]
                while b'\n' in self.buf:
                    line, self.buf = self.buf.split(b'\n', 1)
                    match = SAMPLE.search(line.decode('ascii', errors='ignore'))
                    if match:
                        value = int(match.group(1))
                        on = value >= THRESHOLD
                        self.samples.append(on)
                        self.samples = self.samples[-150:]
                        self.label.config(text=f'{"ON" if on else "OFF"} · {value}', fg='#22C55E' if on else '#EF4444')
                        self.draw()
            except (serial.SerialException, OSError):
                self.ser.close()
                self.ser = None
                self.note.config(text='Serial disconnected; reconnecting...')
        self.root.after(40, self.tick)

    def draw(self):
        c = self.canvas
        c.delete('all')
        w, h = c.winfo_width(), c.winfo_height()
        if w < 20 or h < 20: return
        left, right, top, bottom = 48, w - 12, 20, h - 28
        c.create_line(left, top, left, bottom, fill='#64748b')
        c.create_line(left, bottom, right, bottom, fill='#64748b')
        c.create_text(left - 8, top, text='ON', anchor='e', fill='#9CA3AF')
        c.create_text(left - 8, bottom, text='OFF', anchor='e', fill='#9CA3AF')
        if len(self.samples) > 1:
            points = []
            for i, on in enumerate(self.samples):
                x = left + i * (right - left) / 149
                y = top if on else bottom
                if i: points.extend((x, top if self.samples[i - 1] else bottom))
                points.extend((x, y))
            c.create_line(*points, fill='#38BDF8', width=3)

    def close(self):
        if self.ser and self.ser.is_open: self.ser.close()
        self.root.destroy()

if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('--port', default=None); args = ap.parse_args()
    root = tk.Tk(); app = App(root, args.port)
    root.protocol('WM_DELETE_WINDOW', app.close)
    root.mainloop()
