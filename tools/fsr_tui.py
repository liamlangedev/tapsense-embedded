#!/usr/bin/env python3
"""Minimal dark terminal view of the Nano's A0 sensor state."""
import argparse
import glob
import re
import time

import serial

BAUD = 115200
THRESHOLD = 150
SAMPLE = re.compile(rb"Pad1_A0:(\d+)")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", help="serial port (auto-detect by default)")
    parser.add_argument("--threshold", type=int, default=THRESHOLD)
    args = parser.parse_args()
    ports = [args.port] if args.port else sorted(glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*"))
    ser = None
    port = None
    buf = bytearray()
    state = None
    value = None
    last_try = 0.0
    print("\033[?25l", end="", flush=True)
    try:
        while True:
            if ser is None and time.monotonic() - last_try >= 1:
                last_try = time.monotonic()
                for candidate in ports:
                    try:
                        ser = serial.Serial(candidate, BAUD, timeout=0)
                        port = candidate
                        buf.clear()
                        break
                    except (serial.SerialException, OSError):
                        pass
            if ser is not None:
                try:
                    buf.extend(ser.read(512))
                    if len(buf) > 4096:
                        del buf[:-1024]
                    while b"\n" in buf:
                        line, _, rest = buf.partition(b"\n")
                        buf[:] = rest
                        match = SAMPLE.search(line)
                        if match:
                            value = int(match.group(1))
                            state = value >= args.threshold
                except (serial.SerialException, OSError):
                    ser.close()
                    ser = port = None
                    state = value = None
            status = "ON " if state is True else "OFF" if state is False else "WAITING FOR NANO DATA"
            color = "\033[92m" if state is True else "\033[91m" if state is False else "\033[90m"
            detail = f"A0 {value:4d}   threshold {args.threshold}" if value is not None else "Check Nano USB serial output / 115200 baud"
            print(f"\033[2J\033[H\033[40m\033[97m FSR  /  A0 ON-OFF\n\n {color}{status}\033[0m\n\n\033[90m {detail}\n {port or 'no serial port'}\n\n Ctrl-C to quit\033[0m", end="", flush=True)
            time.sleep(0.08)
    except KeyboardInterrupt:
        pass
    finally:
        if ser is not None:
            ser.close()
        print("\033[0m\033[?25h", end="", flush=True)


if __name__ == "__main__":
    main()
