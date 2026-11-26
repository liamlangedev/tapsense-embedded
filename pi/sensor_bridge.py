#!/usr/bin/env python3
"""Real ESP32 serial -> WebSocket bridge. No mock fallback."""
import asyncio
import json
import sys
import serial
import websockets

PORT = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyACM0"
BAUD = 115200
WS_PORT = 8889

async def main():
    clients = set()
    queue = asyncio.Queue()

    async def websocket_handler(ws):
        clients.add(ws)
        try:
            await ws.wait_closed()
        finally:
            clients.discard(ws)

    async def read_serial():
        try:
            ser = serial.Serial(PORT, BAUD, timeout=0.1)
        except Exception as exc:
            print(f"SERIAL ERROR: {exc}", file=sys.stderr, flush=True)
            return
        print(f"REAL SERIAL: {PORT} @ {BAUD}", file=sys.stderr, flush=True)
        try:
            while True:
                raw = await asyncio.to_thread(ser.readline)
                if not raw:
                    continue
                line = raw.decode("utf-8", errors="replace").strip()
                try:
                    json.loads(line)
                except json.JSONDecodeError:
                    print(f"SERIAL NON-JSON: {line}", file=sys.stderr, flush=True)
                    continue
                await queue.put(line)
        finally:
            ser.close()

    async def broadcast():
        while True:
            line = await queue.get()
            if clients:
                await asyncio.gather(*(ws.send(line) for ws in tuple(clients)), return_exceptions=True)

    async with websockets.serve(websocket_handler, "127.0.0.1", WS_PORT):
        print(f"REAL DASHBOARD SOCKET: ws://127.0.0.1:{WS_PORT}", file=sys.stderr, flush=True)
        await asyncio.gather(read_serial(), broadcast())

try:
    asyncio.run(main())
except KeyboardInterrupt:
    pass
