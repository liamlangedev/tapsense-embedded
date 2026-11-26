/*
 * TapSense v2 — 4-Zone Helmet Impact + Plate Carrier Gesture Hub (ESP8266)
 *
 * Receives the 5-channel labelled CSV stream from the Arduino Nano on D7:
 *   H_N:<int>,H_E:<int>,H_S:<int>,H_W:<int>,P_TAP:<int>\n
 *
 * Features:
 *   1. Directional helmet impact detection (vector sum across N/E/S/W -> 0..359 deg)
 *      with adaptive EMA baseline tracking to reject slow strap tension / leaning.
 *   2. Plate-carrier multi-tap gesture classifier (2 = critical, 3 = medical drone,
 *      4 = backup resupply) with hysteresis and inter-tap timeout.
 *   3. Store-and-forward 16-slot event ring buffer (GET /events?since=<id>) so
 *      a Raspberry Pi consumer recovers missed alerts after a Wi-Fi drop.
 *   4. Gesture events automatically attach the latest helmet impact vector.
 *   5. Live compass + plate status web UI at http://192.168.4.1/ and OLED readout.
 *
 * Wiring: Nano D1/TX --[1k]--+-- ESP D7 (GPIO13 RX)
 *                            |
 *                           [2k]
 *                            |
 *                           GND  (Common ground required)
 */

#include <ESP8266WiFi.h>
#include <ESP8266WebServer.h>
#include <U8g2lib.h>
#include <SoftwareSerial.h>
#include <limits.h>
#include <math.h>
#include <stdint.h>
#include <string.h>

const char *AP_SSID = "FSR-Hub";
const char *AP_PASS = "fsr-sensor";

const size_t LINE_CAPACITY = 128;

// Helmet impact parameters (10-bit ADC 0..1023, 100 Hz input)
const int IMPACT_DELTA_MIN = 120;      // min rise above baseline to start impact
const int IMPACT_DELTA_MED = 320;      // medium severity threshold
const int IMPACT_DELTA_HIGH = 600;     // high severity threshold
const unsigned long IMPACT_WINDOW_MS = 80;    // peak integration window
const unsigned long IMPACT_COOLDOWN_MS = 450; // refractory period
const unsigned long UNRESPONSIVE_ESCALATION_MS = 10000; // auto-medevac if no tap after HIGH impact

// Plate-carrier tap parameters
const int TAP_PRESS_THRESHOLD = 150;
const int TAP_RELEASE_THRESHOLD = 80;
const unsigned long TAP_GAP_MS = 400;

// Store-and-forward ring buffer
const size_t EVENT_RING_SIZE = 16;

struct TapEvent {
  uint32_t id;
  unsigned long timestampMs;
  char kind[16];          // "HELMET_IMPACT" or "GESTURE"
  char eventType[36];     // e.g. "medical_supply_drone_request"
  uint8_t tapCount;
  int16_t directionDeg;   // 0..359 (-1 if none)
  char cardinal[4];       // N, NE, E, SE, S, SW, W, NW, or "-"
  int16_t peakForce;
  char severity[8];       // LOW, MEDIUM, HIGH, NONE
  uint8_t confidence;     // 0..100
  long impactAgeMs;       // age of attached helmet impact for GESTURE events
};

TapEvent eventRing[EVENT_RING_SIZE];
size_t eventHead = 0;
size_t eventCount = 0;
uint32_t nextEventId = 1;

// Live sensor state
bool hasSample = false;
long curN = 0, curE = 0, curS = 0, curW = 0, curTap = 0;
float baseN = 0.0f, baseE = 0.0f, baseS = 0.0f, baseW = 0.0f;
bool baselineInit = false;

// Active impact integration state
bool impactActive = false;
unsigned long impactStartMs = 0;
unsigned long lastImpactAt = 0;
long peakN = 0, peakE = 0, peakS = 0, peakW = 0;

// Last recorded helmet impact (attached to subsequent gesture dispatches)
bool hasLastImpact = false;
unsigned long lastConfirmedImpactMs = 0;
bool pendingEscalation = false;
int16_t lastImpactDeg = -1;
char lastImpactCardinal[4] = "-";
int16_t lastImpactPeak = 0;
char lastImpactSeverity[8] = "NONE";
uint8_t lastImpactConfidence = 0;

// Plate tap state
uint8_t tapCount = 0;
bool tapDown = false;
unsigned long lastTapAt = 0;
uint8_t lastGestureTaps = 0;
char lastGestureType[36] = "none";

unsigned long lastOledAt = 0;

U8G2_SSD1306_128X64_NONAME_F_SW_I2C oled(U8G2_R0, D5, D6, U8X8_PIN_NONE);
SoftwareSerial nanoSerial(D7, -1);
ESP8266WebServer server(80);

char lineBuffer[LINE_CAPACITY];
size_t lineLength = 0;
bool discardingLine = false;

const char PAGE_HTML[] PROGMEM = R"HTML(<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>TapSense v2 — Helmet &amp; Plate</title>
<style>
:root{color-scheme:dark}
body{font:15px/1.5 ui-sans-serif,system-ui,sans-serif;max-width:860px;margin:24px auto;padding:0 14px;background:#0d1117;color:#e5e7eb}
h1{font-size:1.35rem;margin:0 0 4px}
.sub{color:#94a3b8;font-size:.9rem;margin-bottom:16px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}
@media(max-width:680px){.grid{grid-template-columns:1fr}}
.card{background:#161f2c;border:1px solid #2d3a4f;border-radius:10px;padding:14px}
.big{font-size:1.5rem;font-weight:700;color:#38bdf8}
.mono{font-family:ui-monospace,monospace;font-size:.86rem;color:#cbd5e1}
canvas{display:block;margin:8px auto;background:#0b121c;border:1px solid #2d3a4f;border-radius:8px}
</style></head><body>
<h1>TapSense v2 — 4-Zone Helmet &amp; Plate Hub</h1>
<div class="sub" id="status">Connecting to ESP8266…</div>
<div class="grid">
  <div class="card">
    <div><strong>Helmet Impact Compass</strong></div>
    <canvas id="compass" width="220" height="220"></canvas>
    <div class="mono" id="helmetInfo">Waiting for sensor data…</div>
  </div>
  <div class="card">
    <div><strong>Plate Carrier Gesture Pad</strong></div>
    <div class="big" id="gesture">NONE</div>
    <div class="mono" id="plateInfo">A4: —</div>
    <hr style="border:0;border-top:1px solid #2d3a4f;margin:12px 0">
    <div><strong>Recent Events</strong></div>
    <div class="mono" id="events" style="margin-top:6px;max-height:150px;overflow:auto">—</div>
  </div>
</div>
<div class="card" style="margin-top:14px">
  <div><strong>Live Force Waveforms (0–1023)</strong> · <span class="mono">N=cyan E=green S=amber W=violet Plate=pink</span></div>
  <canvas id="wave" width="820" height="210" style="width:100%;height:210px"></canvas>
</div>
<script>
const st=document.getElementById('status'),hi=document.getElementById('helmetInfo'),
      pi=document.getElementById('plateInfo'),ge=document.getElementById('gesture'),
      ev=document.getElementById('events'),cv=document.getElementById('compass'),ctx=cv.getContext('2d'),
      wv=document.getElementById('wave'),wctx=wv.getContext('2d');
let lastSeenId=0, log=[], hist=[[],[],[],[],[]];
const cols=['#38bdf8','#34d399','#fbbf24','#a78bfa','#f472b6'];

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
    if(r.status===503){st.textContent='Waiting for Nano CSV…';}
    else if(r.ok){
      const d=await r.json();
      st.textContent='Live · FSR-Hub (192.168.4.1)';
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
  setTimeout(poll,90);
}
poll();
</script></body></html>)HTML";

void degToCardinal(int16_t deg, char *out) {
  static const char *DIRS[8] = {"N", "NE", "E", "SE", "S", "SW", "W", "NW"};
  if (deg < 0) {
    strcpy(out, "-");
    return;
  }
  int idx = ((deg + 22) % 360) / 45;
  strcpy(out, DIRS[idx]);
}

void pushEvent(const char *kind, const char *eventType, uint8_t taps,
               int16_t dirDeg, const char *cardinal, int16_t peak,
               const char *severity, uint8_t confidence, long impactAgeMs) {
  TapEvent &slot = eventRing[eventHead];
  slot.id = nextEventId++;
  slot.timestampMs = millis();
  strncpy(slot.kind, kind, sizeof(slot.kind) - 1);
  slot.kind[sizeof(slot.kind) - 1] = '\0';
  strncpy(slot.eventType, eventType, sizeof(slot.eventType) - 1);
  slot.eventType[sizeof(slot.eventType) - 1] = '\0';
  slot.tapCount = taps;
  slot.directionDeg = dirDeg;
  strncpy(slot.cardinal, cardinal, sizeof(slot.cardinal) - 1);
  slot.cardinal[sizeof(slot.cardinal) - 1] = '\0';
  slot.peakForce = peak;
  strncpy(slot.severity, severity, sizeof(slot.severity) - 1);
  slot.severity[sizeof(slot.severity) - 1] = '\0';
  slot.confidence = confidence;
  slot.impactAgeMs = impactAgeMs;

  eventHead = (eventHead + 1) % EVENT_RING_SIZE;
  if (eventCount < EVENT_RING_SIZE) {
    ++eventCount;
  }
}

void updateOled() {
  oled.clearBuffer();
  oled.setFont(u8g2_font_6x12_tr);
  oled.drawStr(0, 12, "TapSense v2 Hub");

  oled.setCursor(0, 28);
  if (hasLastImpact) {
    oled.print(F("Hit: "));
    oled.print(lastImpactCardinal);
    oled.print(F(" "));
    oled.print(lastImpactDeg);
    oled.print(F("d "));
    oled.print(lastImpactSeverity);
  } else {
    oled.print(F("Helmet: listening"));
  }

  oled.setCursor(0, 44);
  if (lastGestureTaps == 2) oled.print(F("2 taps: CRITICAL"));
  else if (lastGestureTaps == 3) oled.print(F("3 taps: MEDICAL"));
  else if (lastGestureTaps == 4) oled.print(F("4 taps: BACKUP"));
  else if (tapCount > 0) {
    oled.print(F("Plate taps: "));
    oled.print(tapCount);
  } else {
    oled.print(F("Plate: 2/3/4 taps"));
  }

  oled.setCursor(0, 60);
  oled.print(hasSample ? F("Nano OK | 192.168.4.1") : F("Waiting for Nano"));
  oled.sendBuffer();
}

void finalizeImpact(unsigned long now) {
  impactActive = false;
  lastImpactAt = now;

  const long maxPeak = max(max(peakN, peakE), max(peakS, peakW));
  if (maxPeak < IMPACT_DELTA_MIN) {
    return;
  }

  // Vector sum across 4 orthogonal helmet zones:
  //   +Y = North (Front), +X = East (Right)
  const float vx = static_cast<float>(peakE - peakW);
  const float vy = static_cast<float>(peakN - peakS);
  const float mag = sqrtf(vx * vx + vy * vy);

  int16_t deg = 0;
  if (mag >= 10.0f) {
    float angle = atan2f(vx, vy) * (180.0f / 3.14159265f);
    if (angle < 0.0f) angle += 360.0f;
    deg = static_cast<int16_t>(lroundf(angle)) % 360;
  }

  char card[4];
  degToCardinal(deg, card);

  const char *sev = "LOW";
  if (maxPeak >= IMPACT_DELTA_HIGH) sev = "HIGH";
  else if (maxPeak >= IMPACT_DELTA_MED) sev = "MEDIUM";

  // Confidence scales with signal-to-threshold margin and directional clarity
  const long totalSum = peakN + peakE + peakS + peakW;
  const float dirRatio = (totalSum > 0) ? (mag / static_cast<float>(totalSum)) : 0.0f;
  int conf = 50 + static_cast<int>((maxPeak - IMPACT_DELTA_MIN) / 15) + static_cast<int>(dirRatio * 25.0f);
  if (conf > 99) conf = 99;
  if (conf < 30) conf = 30;

  hasLastImpact = true;
  lastConfirmedImpactMs = now;
  pendingEscalation = (strcmp(sev, "HIGH") == 0);
  lastImpactDeg = deg;
  strcpy(lastImpactCardinal, card);
  lastImpactPeak = static_cast<int16_t>(maxPeak);
  strcpy(lastImpactSeverity, sev);
  lastImpactConfidence = static_cast<uint8_t>(conf);

  pushEvent("HELMET_IMPACT", "helmet_impact_detected", 0,
            deg, card, lastImpactPeak, sev, lastImpactConfidence, 0);
  updateOled();
}

void processHelmetSample(long n, long e, long s, long w) {
  const unsigned long now = millis();
  if (!baselineInit) {
    baseN = static_cast<float>(n);
    baseE = static_cast<float>(e);
    baseS = static_cast<float>(s);
    baseW = static_cast<float>(w);
    baselineInit = true;
    return;
  }

  const long dN = max(0L, n - static_cast<long>(baseN));
  const long dE = max(0L, e - static_cast<long>(baseE));
  const long dS = max(0L, s - static_cast<long>(baseS));
  const long dW = max(0L, w - static_cast<long>(baseW));
  const long maxD = max(max(dN, dE), max(dS, dW));

  if (!impactActive) {
    // Track slow drift only when idle
    const float alpha = 0.05f;
    baseN = (1.0f - alpha) * baseN + alpha * static_cast<float>(n);
    baseE = (1.0f - alpha) * baseE + alpha * static_cast<float>(e);
    baseS = (1.0f - alpha) * baseS + alpha * static_cast<float>(s);
    baseW = (1.0f - alpha) * baseW + alpha * static_cast<float>(w);

    if (maxD >= IMPACT_DELTA_MIN && (now - lastImpactAt >= IMPACT_COOLDOWN_MS)) {
      impactActive = true;
      impactStartMs = now;
      peakN = dN;
      peakE = dE;
      peakS = dS;
      peakW = dW;
    }
  } else {
    if (dN > peakN) peakN = dN;
    if (dE > peakE) peakE = dE;
    if (dS > peakS) peakS = dS;
    if (dW > peakW) peakW = dW;

    if (now - impactStartMs >= IMPACT_WINDOW_MS) {
      finalizeImpact(now);
    }
  }
}

void processPlateTap(long value) {
  const unsigned long now = millis();
  if (!tapDown && value >= TAP_PRESS_THRESHOLD) {
    pendingEscalation = false;  // soldier is responsive
    if (!tapCount || now - lastTapAt > TAP_GAP_MS) {
      tapCount = 0;
    }
    if (tapCount < 5) ++tapCount;
    lastTapAt = now;
    tapDown = true;
  } else if (tapDown && value <= TAP_RELEASE_THRESHOLD) {
    tapDown = false;
  }

  if (tapCount && !tapDown && (now - lastTapAt >= TAP_GAP_MS)) {
    if (tapCount >= 2 && tapCount <= 4) {
      lastGestureTaps = tapCount;
      const char *etype =
          (tapCount == 2) ? "critical_situation" :
          (tapCount == 3) ? "medical_supply_drone_request" :
                            "backup_resupply_request";
      strncpy(lastGestureType, etype, sizeof(lastGestureType) - 1);
      lastGestureType[sizeof(lastGestureType) - 1] = '\0';

      const long ageMs = hasLastImpact ? static_cast<long>(now - lastConfirmedImpactMs) : -1;
      pushEvent("GESTURE", etype, tapCount,
                lastImpactDeg, lastImpactCardinal, lastImpactPeak,
                lastImpactSeverity, lastImpactConfidence, ageMs);
      updateOled();
    }
    tapCount = 0;
  }
}

bool parseFiveChannelCsv(const char *line, long &n, long &e, long &s, long &w, long &tap) {
  long vals[5] = {-1, -1, -1, -1, -1};
  const char *field = line;
  while (*field) {
    const char *end = strchr(field, ',');
    const size_t len = end ? static_cast<size_t>(end - field) : strlen(field);
    const char *sep = static_cast<const char *>(memchr(field, ':', len));
    if (sep) {
      const size_t klen = static_cast<size_t>(sep - field);
      int idx = -1;
      if (klen == 3 && memcmp(field, "H_N", 3) == 0) idx = 0;
      else if (klen == 3 && memcmp(field, "H_E", 3) == 0) idx = 1;
      else if (klen == 3 && memcmp(field, "H_S", 3) == 0) idx = 2;
      else if (klen == 3 && memcmp(field, "H_W", 3) == 0) idx = 3;
      else if (klen == 5 && memcmp(field, "P_TAP", 5) == 0) idx = 4;

      if (idx >= 0) {
        const char *digit = sep + 1;
        if (digit == field + len) return false;
        long parsed = 0;
        while (digit < field + len) {
          if (*digit < '0' || *digit > '9') return false;
          const int d = *digit++ - '0';
          if (parsed > (LONG_MAX - d) / 10) return false;
          parsed = parsed * 10 + d;
        }
        vals[idx] = parsed;
      }
    }
    if (!end) break;
    field = end + 1;
  }
  for (int i = 0; i < 5; ++i) {
    if (vals[i] < 0) return false;
  }
  n = vals[0]; e = vals[1]; s = vals[2]; w = vals[3]; tap = vals[4];
  return true;
}

void handleData() {
  if (!hasSample) {
    server.send(503, "application/json", "{\"error\":\"waiting_for_nano\"}");
    return;
  }
  char json[384];
  snprintf(json, sizeof(json),
           "{\"helmet\":{\"n\":%ld,\"e\":%ld,\"s\":%ld,\"w\":%ld,"
           "\"direction_deg\":%d,\"cardinal\":\"%s\",\"peak\":%d,"
           "\"severity\":\"%s\",\"confidence\":%u},"
           "\"plate\":{\"a4\":%ld,\"pressed\":%s},"
           "\"gesture\":{\"tap_count\":%u,\"event_type\":\"%s\"}}",
           curN, curE, curS, curW,
           static_cast<int>(lastImpactDeg), lastImpactCardinal,
           static_cast<int>(lastImpactPeak), lastImpactSeverity,
           static_cast<unsigned>(lastImpactConfidence),
           curTap, (curTap >= TAP_PRESS_THRESHOLD) ? "true" : "false",
           static_cast<unsigned>(lastGestureTaps), lastGestureType);
  server.send(200, "application/json", json);
}

void handleEvents() {
  uint32_t sinceId = 0;
  if (server.hasArg("since")) {
    sinceId = static_cast<uint32_t>(strtoul(server.arg("since").c_str(), nullptr, 10));
  }

  String out;
  out.reserve(1024);
  out += "{\"events\":[";

  bool first = true;
  const size_t start = (eventHead + EVENT_RING_SIZE - eventCount) % EVENT_RING_SIZE;
  for (size_t i = 0; i < eventCount; ++i) {
    const TapEvent &ev = eventRing[(start + i) % EVENT_RING_SIZE];
    if (ev.id <= sinceId) continue;

    char item[256];
    snprintf(item, sizeof(item),
             "%s{\"id\":%lu,\"ts_ms\":%lu,\"kind\":\"%s\",\"event_type\":\"%s\","
             "\"tap_count\":%u,\"direction_deg\":%d,\"cardinal\":\"%s\","
             "\"peak_force\":%d,\"severity\":\"%s\",\"confidence\":%u,"
             "\"impact_age_ms\":%ld}",
             first ? "" : ",",
             static_cast<unsigned long>(ev.id),
             ev.timestampMs,
             ev.kind,
             ev.eventType,
             static_cast<unsigned>(ev.tapCount),
             static_cast<int>(ev.directionDeg),
             ev.cardinal,
             static_cast<int>(ev.peakForce),
             ev.severity,
             static_cast<unsigned>(ev.confidence),
             ev.impactAgeMs);
    out += item;
    first = false;
  }
  out += "]}";
  server.send(200, "application/json", out);
}

void handleSerial() {
  while (nanoSerial.available()) {
    const char c = static_cast<char>(nanoSerial.read());
    if (c == '\r') continue;
    if (c == '\n') {
      if (!discardingLine) {
        lineBuffer[lineLength] = '\0';
        long n, e, s, w, tap;
        if (parseFiveChannelCsv(lineBuffer, n, e, s, w, tap)) {
          hasSample = true;
          curN = n; curE = e; curS = s; curW = w; curTap = tap;
          processHelmetSample(n, e, s, w);
          processPlateTap(tap);
        }
      }
      lineLength = 0;
      discardingLine = false;
    } else if (!discardingLine) {
      if (lineLength + 1 < LINE_CAPACITY) {
        lineBuffer[lineLength++] = c;
      } else {
        lineLength = 0;
        discardingLine = true;
      }
    }
  }
}

void setup() {
  Serial.begin(115200);
  nanoSerial.begin(115200);
  oled.begin();
  updateOled();

  WiFi.mode(WIFI_AP);
  WiFi.softAP(AP_SSID, AP_PASS);

  server.on("/", HTTP_GET, []() { server.send_P(200, "text/html", PAGE_HTML); });
  server.on("/data", HTTP_GET, handleData);
  server.on("/events", HTTP_GET, handleEvents);
  server.begin();
}

void checkUnresponsiveEscalation() {
  if (!pendingEscalation) return;
  const unsigned long now = millis();
  if (now - lastConfirmedImpactMs >= UNRESPONSIVE_ESCALATION_MS) {
    pendingEscalation = false;
    strncpy(lastGestureType, "auto_medevac_unresponsive", sizeof(lastGestureType) - 1);
    lastGestureType[sizeof(lastGestureType) - 1] = '\0';
    pushEvent("AUTO_ESCALATION", "auto_medevac_unresponsive", 0,
              lastImpactDeg, lastImpactCardinal, lastImpactPeak,
              lastImpactSeverity, lastImpactConfidence,
              static_cast<long>(now - lastConfirmedImpactMs));
    updateOled();
  }
}

void loop() {
  handleSerial();
  checkUnresponsiveEscalation();
  if (millis() - lastOledAt >= 1000) {
    lastOledAt = millis();
    updateOled();
  }
  server.handleClient();
}
