#!/usr/bin/env python3
"""Interactive browser simulator for TapSense v2 (4-Zone Helmet + Plate Carrier).

Runs the exact same HTTP contract (/data and /events?since=<id>) as the ESP8266
v2 hub locally on http://127.0.0.1:8080, with interactive trigger buttons so the
compass, 5-channel analog force waveforms, gesture classifier, and auto-medevac
escalation can be demonstrated without physical hardware attached.

Usage:
    python3 tools/sim_v2_hub.py
    python3 tools/sim_v2_hub.py --port 8080
"""
import argparse
import json
import math
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

LOCK = threading.Lock()
START_TIME = time.monotonic()

STATE = {
    "n": 18,
    "e": 14,
    "s": 16,
    "w": 15,
    "a4": 10,
    "pressed": False,
    "direction_deg": -1,
    "cardinal": "-",
    "peak": 0,
    "severity": "NONE",
    "confidence": 0,
    "tap_count": 0,
    "event_type": "none",
    "last_impact_ts": 0.0,
    "pending_escalation": False,
    "next_event_id": 1,
    "events": [],
}

# Active impulse animations [(t0, duration, ch_peaks_dict, is_tap)]
PULSES = []

CARDINALS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]

HTML_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>TapSense v2 — Interactive Simulator</title>
<style>
:root{color-scheme:dark}
body{font:15px/1.5 ui-sans-serif,system-ui,sans-serif;max-width:920px;margin:22px auto;padding:0 14px;background:#0d1117;color:#e5e7eb}
h1{font-size:1.35rem;margin:0 0 4px}
.sub{color:#94a3b8;font-size:.9rem;margin-bottom:14px}
.controls{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:14px}
button{background:#1e293b;color:#e2e8f0;border:1px solid #334155;border-radius:8px;padding:7px 12px;cursor:pointer;font-size:.86rem}
button:hover{border-color:#38bdf8;color:#38bdf8}
button.danger{border-color:#ef444488;color:#fca5a5}
button.danger:hover{border-color:#ef4444;color:#fecaca}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}
@media(max-width:700px){.grid{grid-template-columns:1fr}}
.card{background:#161f2c;border:1px solid #2d3a4f;border-radius:10px;padding:14px}
.big{font-size:1.35rem;font-weight:700;color:#38bdf8}
.mono{font-family:ui-monospace,monospace;font-size:.85rem;color:#cbd5e1}
canvas{display:block;margin:8px auto;background:#0b121c;border:1px solid #2d3a4f;border-radius:8px}
</style></head><body>
<h1>TapSense v2 — Interactive Simulator</h1>
<div class="sub" id="status">Connecting to local simulator…</div>
<div class="controls">
  <button onclick="trig('/sim/impact?deg=0&force=460')">Hit Front (0°)</button>
  <button onclick="trig('/sim/impact?deg=45&force=520')">Hit NE (45°)</button>
  <button onclick="trig('/sim/impact?deg=90&force=490')">Hit Right (90°)</button>
  <button onclick="trig('/sim/impact?deg=180&force=440')">Hit Back (180°)</button>
  <button onclick="trig('/sim/impact?deg=270&force=510')">Hit Left (270°)</button>
  <button class="danger" onclick="trig('/sim/impact?deg=315&force=860')">Heavy Hit NW (Auto-Medevac 5s)</button>
  <button onclick="trig('/sim/tap?count=2')">2 Taps (Critical)</button>
  <button onclick="trig('/sim/tap?count=3')">3 Taps (Medical Drone)</button>
  <button onclick="trig('/sim/tap?count=4')">4 Taps (Backup)</button>
</div>
<div class="grid">
  <div class="card">
    <div><strong>Helmet Impact Compass</strong></div>
    <canvas id="compass" width="220" height="220"></canvas>
    <div class="mono" id="helmetInfo">Waiting…</div>
  </div>
  <div class="card">
    <div><strong>Plate Carrier Gesture Pad</strong></div>
    <div class="big" id="gesture">NONE</div>
    <div class="mono" id="plateInfo">A4: —</div>
    <hr style="border:0;border-top:1px solid #2d3a4f;margin:12px 0">
    <div><strong>Store-and-Forward Event Feed</strong></div>
    <div class="mono" id="events" style="margin-top:6px;max-height:150px;overflow:auto">—</div>
  </div>
</div>
<div class="card" style="margin-top:14px">
  <div><strong>Live Force Waveforms (0–1023)</strong> · <span class="mono">N=cyan E=green S=amber W=violet Plate=pink</span></div>
  <canvas id="wave" width="880" height="220" style="width:100%;height:220px"></canvas>
</div>
<script>
const st=document.getElementById('status'),hi=document.getElementById('helmetInfo'),
      pi=document.getElementById('plateInfo'),ge=document.getElementById('gesture'),
      ev=document.getElementById('events'),cv=document.getElementById('compass'),ctx=cv.getContext('2d'),
      wv=document.getElementById('wave'),wctx=wv.getContext('2d');
let lastSeenId=0, log=[], hist=[[],[],[],[],[]];
const cols=['#38bdf8','#34d399','#fbbf24','#a78bfa','#f472b6'];

async function trig(url){ await fetch(url, {method:'POST'}); }

function drawCompass(deg, card, n, e, s, w){
  const cx=110, cy=110, r=82;
  ctx.clearRect(0,0,220,220);
  ctx.strokeStyle='#334155'; ctx.lineWidth=2;
  ctx.beginPath(); ctx.arc(cx,cy,r,0,Math.PI*2); ctx.stroke();
  ctx.fillStyle='#94a3b8'; ctx.font='12px ui-monospace,monospace'; ctx.textAlign='center';
  ctx.fillText('N '+n, cx, 18); ctx.fillText('S '+s, cx, 210);
  ctx.fillText('W '+w, 26, cy+4); ctx.fillText('E '+e, 194, cy+4);
  if(deg>=0){
    const rad=(deg-90)*Math.PI/180;
    ctx.strokeStyle='#f59e0b'; ctx.lineWidth=4;
    ctx.beginPath(); ctx.moveTo(cx,cy);
    ctx.lineTo(cx+Math.cos(rad)*(r-14), cy+Math.sin(rad)*(r-14)); ctx.stroke();
    ctx.fillStyle='#fbbf24'; ctx.font='bold 15px ui-monospace,monospace';
    ctx.fillText(card+' '+deg+'°', cx, cy+5);
  }
}

function drawWaves(){
  const w=wv.width, h=wv.height, top=14, bot=h-20;
  wctx.clearRect(0,0,w,h);
  wctx.strokeStyle='#334155'; wctx.beginPath();
  wctx.moveTo(40,top); wctx.lineTo(40,bot); wctx.lineTo(w-8,bot); wctx.stroke();
  wctx.fillStyle='#94a3b8'; wctx.font='11px ui-monospace,monospace';
  wctx.fillText('1023',4,top+8); wctx.fillText('0',24,bot);
  hist.forEach((arr,ci)=>{
    if(arr.length<2)return;
    wctx.strokeStyle=cols[ci]; wctx.lineWidth=2; wctx.beginPath();
    arr.forEach((v,i)=>{
      const x=40+i*(w-50)/149, y=bot-(Math.min(1023,Math.max(0,v))/1023)*(bot-top);
      i?wctx.lineTo(x,y):wctx.moveTo(x,y);
    });
    wctx.stroke();
  });
}

async function poll(){
  try{
    const r=await fetch('/data',{cache:'no-store'});
    if(r.ok){
      const d=await r.json();
      st.textContent='Live Simulator · same JSON contract as ESP8266 v2';
      drawCompass(d.helmet.direction_deg, d.helmet.cardinal, d.helmet.n, d.helmet.e, d.helmet.s, d.helmet.w);
      [d.helmet.n,d.helmet.e,d.helmet.s,d.helmet.w,d.plate.a4].forEach((v,i)=>{
        hist[i].push(v); if(hist[i].length>150) hist[i].shift();
      });
      drawWaves();
      hi.textContent=`Peak: ${d.helmet.peak} | Sev: ${d.helmet.severity} | Conf: ${d.helmet.confidence}%`;
      pi.textContent=`A4: ${d.plate.a4}/1023 · ${d.plate.pressed?'PRESSED':'IDLE'}`;
      ge.textContent=d.gesture.event_type.toUpperCase();
    }
    const er=await fetch('/events?since='+lastSeenId,{cache:'no-store'});
    if(er.ok){
      const ed=await er.json();
      for(const item of ed.events){
        if(item.id>lastSeenId) lastSeenId=item.id;
        log.unshift(`#${item.id} [${item.kind}] ${item.event_type} dir=${item.cardinal}(${item.direction_deg}°)`);
      }
      if(log.length>12) log.length=12;
      if(log.length) ev.innerHTML=log.map(x=>`<div>${x}</div>`).join('');
    }
  }catch(err){st.textContent='Disconnected ('+err.message+')';}
  setTimeout(poll,60);
}
poll();
</script></body></html>
"""


def deg_to_cardinal(deg: int) -> str:
    return CARDINALS[((deg + 22) % 360) // 45] if deg >= 0 else "-"


def push_event(kind: str, etype: str, taps: int, age_ms: int) -> None:
    eid = STATE["next_event_id"]
    STATE["next_event_id"] += 1
    STATE["events"].append({
        "id": eid,
        "ts_ms": int((time.monotonic() - START_TIME) * 1000),
        "kind": kind,
        "event_type": etype,
        "tap_count": taps,
        "direction_deg": STATE["direction_deg"],
        "cardinal": STATE["cardinal"],
        "peak_force": STATE["peak"],
        "severity": STATE["severity"],
        "confidence": STATE["confidence"],
        "impact_age_ms": age_ms,
    })
    if len(STATE["events"]) > 32:
        STATE["events"] = STATE["events"][-32:]


def trigger_impact(deg: int, force: int) -> None:
    rad = math.radians(deg)
    vy = math.cos(rad)
    vx = math.sin(rad)
    peaks = {
        "n": int(max(0.0, vy) * force),
        "e": int(max(0.0, vx) * force),
        "s": int(max(0.0, -vy) * force),
        "w": int(max(0.0, -vx) * force),
    }
    now = time.monotonic()
    with LOCK:
        PULSES.append((now, 0.35, peaks))
        STATE["direction_deg"] = deg % 360
        STATE["cardinal"] = deg_to_cardinal(STATE["direction_deg"])
        STATE["peak"] = force
        STATE["severity"] = "HIGH" if force >= 600 else "MEDIUM" if force >= 320 else "LOW"
        STATE["confidence"] = min(99, 68 + force // 30)
        STATE["last_impact_ts"] = now
        STATE["pending_escalation"] = (STATE["severity"] == "HIGH")
        push_event("HELMET_IMPACT", "helmet_impact_detected", 0, 0)


def trigger_tap(count: int) -> None:
    etype = {
        2: "critical_situation",
        3: "medical_supply_drone_request",
        4: "backup_resupply_request",
    }.get(count, "none")
    now = time.monotonic()
    with LOCK:
        for i in range(count):
            PULSES.append((now + i * 0.16, 0.11, {"a4": 680}))
        STATE["pending_escalation"] = False
        STATE["tap_count"] = count
        STATE["event_type"] = etype
        age_ms = (
            int((now - STATE["last_impact_ts"]) * 1000)
            if STATE["last_impact_ts"] > 0
            else -1
        )
        push_event("GESTURE", etype, count, age_ms)


def sim_loop() -> None:
    while True:
        now = time.monotonic()
        with LOCK:
            base = {"n": 18, "e": 14, "s": 16, "w": 15, "a4": 10}
            active = []
            for t0, dur, peaks in PULSES:
                dt = now - t0
                if dt < 0:
                    active.append((t0, dur, peaks))
                    continue
                if dt <= dur:
                    env = math.sin(math.pi * dt / dur)
                    for k, pk in peaks.items():
                        base[k] += int(pk * env)
                    active.append((t0, dur, peaks))
            PULSES[:] = active
            for k in ("n", "e", "s", "w", "a4"):
                STATE[k] = min(1023, base[k])
            STATE["pressed"] = STATE["a4"] >= 150

            # Auto-Medevac escalation (5s accelerated window in simulator)
            if STATE["pending_escalation"] and (now - STATE["last_impact_ts"] >= 5.0):
                STATE["pending_escalation"] = False
                STATE["event_type"] = "auto_medevac_unresponsive"
                push_event("AUTO_ESCALATION", "auto_medevac_unresponsive", 0, 5000)
        time.sleep(0.03)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return

    def _send(self, code: int, ctype: str, body: bytes) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/":
            self._send(200, "text/html; charset=utf-8", HTML_PAGE.encode("utf-8"))
        elif u.path == "/data":
            with LOCK:
                payload = {
                    "helmet": {
                        "n": STATE["n"], "e": STATE["e"],
                        "s": STATE["s"], "w": STATE["w"],
                        "direction_deg": STATE["direction_deg"],
                        "cardinal": STATE["cardinal"],
                        "peak": STATE["peak"],
                        "severity": STATE["severity"],
                        "confidence": STATE["confidence"],
                    },
                    "plate": {"a4": STATE["a4"], "pressed": STATE["pressed"]},
                    "gesture": {
                        "tap_count": STATE["tap_count"],
                        "event_type": STATE["event_type"],
                    },
                }
            self._send(200, "application/json", json.dumps(payload).encode("utf-8"))
        elif u.path == "/events":
            qs = parse_qs(u.query)
            since = int(qs.get("since", ["0"])[0])
            with LOCK:
                evs = [e for e in STATE["events"] if e["id"] > since]
            self._send(200, "application/json", json.dumps({"events": evs}).encode("utf-8"))
        else:
            self._send(404, "text/plain", b"not found")

    def do_POST(self):
        u = urlparse(self.path)
        qs = parse_qs(u.query)
        if u.path == "/sim/impact":
            deg = int(qs.get("deg", ["0"])[0])
            force = int(qs.get("force", ["480"])[0])
            trigger_impact(deg, force)
            self._send(200, "application/json", b'{"ok":true}')
        elif u.path == "/sim/tap":
            cnt = int(qs.get("count", ["3"])[0])
            trigger_tap(cnt)
            self._send(200, "application/json", b'{"ok":true}')
        else:
            self._send(404, "text/plain", b"not found")


def main() -> None:
    ap = argparse.ArgumentParser(description="TapSense v2 interactive browser simulator")
    ap.add_argument("--port", type=int, default=8080, help="HTTP port (default 8080)")
    args = ap.parse_args()

    threading.Thread(target=sim_loop, daemon=True).start()
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"TapSense v2 simulator running at http://127.0.0.1:{args.port}/")
    print(f"Pair with Pi client: python3 pi/tapsense_pi_client.py --hub http://127.0.0.1:{args.port}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
