#!/usr/bin/env python3
"""Print only real serial readings; never generates mock values."""
import json
import sys
import time
import serial

PORT = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyACM0"
BAUD = 115200

ser = serial.Serial(PORT, BAUD, timeout=0.09)
print(f"REAL SENSOR: {PORT} @ {BAUD}; one line every 100 ms", flush=True)
print("No bytes means NO DATA, not zero amps.", flush=True)

try:
    next_tick = time.monotonic()
    while True:
        next_tick += 0.1
        raw = ser.readline()
        if not raw:
            print(f"{time.monotonic():.3f}  NO_DATA", flush=True)
        else:
            line = raw.decode("utf-8", errors="replace").strip()
            try:
                data = json.loads(line)
                if "current_a" in data:
                    print(f"{data.get('timestamp_ms', '-') } ms  {data['current_a']:.6f} A  "
                          f"{data.get('voltage_v', '-') } V  raw={data.get('raw_adc', '-')}", flush=True)
                else:
                    print(f"{line}  [no current_a field]", flush=True)
            except json.JSONDecodeError:
                print(f"SERIAL: {line}", flush=True)
        time.sleep(max(0, next_tick - time.monotonic()))
except KeyboardInterrupt:
    pass
finally:
    ser.close()
