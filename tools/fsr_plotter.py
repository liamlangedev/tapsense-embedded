#!/usr/bin/env python3
"""
FSR Single Pad Plotter — IO32 only.
Serial format: IO32: NNN  (X.XXV)
Window never closes, auto-reconnects.
"""

import argparse
import glob
import re
import time
from collections import deque

import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import serial

WINDOW    = 200
BAUD      = 115200
THRESHOLD = 2000


def find_port():
    for pattern in ('/dev/ttyUSB*', '/dev/ttyACM*'):
        hits = sorted(glob.glob(pattern))
        if hits:
            return hits[0]
    return None


class SerialReader:
    def __init__(self, port_override=None):
        self._port_override = port_override
        self._ser  = None
        self._buf  = b''
        self._last_try = 0.0

    def _try_connect(self):
        now = time.monotonic()
        if now - self._last_try < 1.0:
            return
        self._last_try = now
        port = self._port_override or find_port()
        if not port:
            return
        try:
            self._ser = serial.Serial(port, BAUD, timeout=0)
            self._buf = b''
            print(f'[serial] connected: {port}')
        except Exception as e:
            self._ser = None
            print(f'[serial] connect failed: {e}')

    def read_sample(self):
        if self._ser is None or not self._ser.is_open:
            self._try_connect()
            return None
        try:
            chunk = self._ser.read(512)
            if chunk:
                self._buf += chunk
            while b'\n' in self._buf:
                line, self._buf = self._buf.split(b'\n', 1)
                line = line.decode('utf-8', errors='ignore').strip()
                if not line:
                    continue
                # format: "IO32: 3201  (2.58V)"
                m = re.search(r'IO32:\s*(\d+)', line)
                if m:
                    return int(m.group(1))
        except Exception as e:
            print(f'[serial] error: {e} — reconnecting')
            try:
                self._ser.close()
            except Exception:
                pass
            self._ser = None
        return None


# ---- Figure ----------------------------------------------------------------
fig, ax = plt.subplots(figsize=(10, 4))
fig.canvas.manager.set_window_title('FSR Live Plotter — IO32')
fig.patch.set_facecolor('#0A0D12')
ax.set_facecolor('#0F131C')

buf = deque([0] * WINDOW, maxlen=WINDOW)

ax.set_ylim(-50, 4145)
ax.set_xlim(0, WINDOW)
ax.set_ylabel('ADC (0–4095)', color='#9CA3AF')
ax.set_xlabel('Samples', color='#9CA3AF')
ax.tick_params(colors='#9CA3AF')
ax.grid(True, alpha=0.2, color='#374151')
ax.axhline(THRESHOLD, color='#F59E0B', linewidth=1, linestyle='--', alpha=0.7, label='threshold 2000')
for spine in ax.spines.values():
    spine.set_edgecolor('#1E2636')

line_art, = ax.plot(range(WINDOW), list(buf), color='#EF4444', linewidth=2)
status_txt = fig.text(0.5, 0.01, 'Waiting for ESP32...', ha='center',
                      fontsize=10, color='#6B7280')

plt.tight_layout(rect=[0, 0.05, 1, 1])

# ---- Animation -------------------------------------------------------------
_reader = None
_tick   = 0

def update(_frame):
    global _tick
    _tick += 1
    val = _reader.read_sample()
    if val is None:
        if _tick % 20 == 0:
            port = _reader._port_override or find_port() or 'none'
            status_txt.set_text(f'Waiting for ESP32 on {port}...')
        return
    buf.append(val)
    line_art.set_ydata(list(buf))
    voltage = (val / 4095.0) * 3.3
    status_txt.set_text(f'IO32 = {val:4d}  ({voltage:.2f}V)   {"PRESSED" if val < THRESHOLD else "idle"}')
    print(f'IO32={val:4d}  {voltage:.2f}V')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', default=None)
    args = parser.parse_args()
    _reader = SerialReader(port_override=args.port)
    ani = animation.FuncAnimation(fig, update, interval=50, blit=False, cache_frame_data=False)
    plt.show()
