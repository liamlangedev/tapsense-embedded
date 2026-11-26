/*
 * TapSense — ESP8266 FSR Hub
 *
 * Receives the Nano's labelled CSV stream (Pad1_A0:<int>,...) on a software
 * UART (D7) and exposes the latest Zone-1 pressure value over Wi-Fi.
 *
 * - Runs as its own access point: SSID "FSR-Hub", password "fsr-sensor"
 * - Serves a live on/off graph at http://192.168.4.1/
 * - Serves the raw value as JSON at http://192.168.4.1/data
 * - Shows status + multi-tap classification on the onboard SSD1306 OLED
 *
 * Wiring: Nano D1/TX --1k-- ESP D7 (GPIO13), ESP D7 --2k-- GND.
 * The divider is mandatory: the Nano drives 5 V, the ESP8266 is 3.3 V only.
 *
 * NOTE: This is the state as of the hackathon demo. The tap->event mapping
 * (2 taps = critical, 3 = medical drone, 4 = backup resupply) is shown on the
 * OLED but is NOT yet part of the /data JSON contract. See docs/PROTOCOL.md.
 */

#include <ESP8266WiFi.h>
#include <ESP8266WebServer.h>
#include <U8g2lib.h>
#include <SoftwareSerial.h>
#include <limits.h>
#include <stdint.h>
#include <string.h>

const char *apSsid = "FSR-Hub";
const char *apPassword = "fsr-sensor";
const size_t lineCapacity = 96;
const int tapPressThreshold = 150;
const int tapReleaseThreshold = 80;
const unsigned long tapGapMs = 400;

uint8_t tapCount = 0;
bool tapDown = false;
unsigned long lastTapAt = 0;
uint32_t eventId = 0;
unsigned long lastOledAt = 0;
uint8_t eventTapCount = 0;

U8G2_SSD1306_128X64_NONAME_F_SW_I2C oled(U8G2_R0, D5, D6, U8X8_PIN_NONE);
SoftwareSerial nanoSerial(D7, -1);
ESP8266WebServer server(80);
char lineBuffer[lineCapacity];
size_t lineLength = 0;
bool discardingLine = false;
bool hasSample = false;
long latestA0 = 0;

const char page[] PROGMEM = R"HTML(<!doctype html>
<html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Nano FSR live</title><style>
body{font:16px sans-serif;max-width:760px;margin:24px auto;padding:0 12px;background:#111827;color:#eee}
.value{font-size:2rem}canvas{width:100%;height:280px;border:1px solid #64748b}
</style></head><body><h1>FSR on/off</h1><div id="status">Connecting to NodeMCU…</div>
<div>Sensor A0: <span class="value" id="value">—</span> · <span id="state">Waiting</span></div>
<canvas id="graph" width="760" height="280"></canvas>
<script>
const status=document.getElementById('status'),value=document.getElementById('value'),state=document.getElementById('state'),canvas=document.getElementById('graph'),ctx=canvas.getContext('2d'),samples=[];
async function poll(){try{const r=await fetch('/data',{cache:'no-store'});if(!r.ok)throw Error('HTTP '+r.status);const d=await r.json();status.textContent='Live';value.textContent=d.a0;state.textContent=d.pressed?'ON':'OFF';samples.push(d.pressed?1:0);if(samples.length>150)samples.shift();draw();}catch(e){status.textContent='Waiting for sensor data ('+e.message+')';}setTimeout(poll,100);}
function draw(){const w=canvas.width,h=canvas.height,top=24,bottom=h-30;ctx.clearRect(0,0,w,h);ctx.strokeStyle='#64748b';ctx.beginPath();ctx.moveTo(40,top);ctx.lineTo(40,bottom);ctx.lineTo(w-8,bottom);ctx.stroke();ctx.fillStyle='#cbd5e1';ctx.fillText('ON',8,top+5);ctx.fillText('OFF',8,bottom);ctx.strokeStyle='#38bdf8';ctx.beginPath();samples.forEach((v,i)=>{const x=40+i*(w-50)/149,y=v?top:bottom;if(i===0)ctx.moveTo(x,y);else{ctx.lineTo(x,samples[i-1]?top:bottom);ctx.lineTo(x,y);}});ctx.stroke();}
poll();
</script></body></html>)HTML";

void updateOled() {
  oled.clearBuffer();
  oled.setFont(u8g2_font_6x12_tr);
  oled.drawStr(0, 12, "Nano FSR live");
  oled.setCursor(0, 28);
  oled.print(F("Peak: "));
  oled.print(latestA0);
  oled.setCursor(0, 44);
  if (eventTapCount == 2) oled.print(F("2 taps: CRITICAL"));
  else if (eventTapCount == 3) oled.print(F("3 taps: MEDICAL"));
  else if (eventTapCount == 4) oled.print(F("4 taps: BACKUP"));
  else if (tapCount) {
    oled.print(F("Tap count: "));
    oled.print(tapCount);
  } else oled.print(F("Tap 2 / 3 / 4 times"));
  oled.setCursor(0, 60);
  oled.print(hasSample ? F("Nano connected") : F("Waiting for Nano"));
  oled.sendBuffer();
}

void updateTapEvent(long value) {
  const unsigned long now = millis();
  if (!tapDown && value >= tapPressThreshold) {
    if (!tapCount || now - lastTapAt > tapGapMs) tapCount = 0;
    if (tapCount < 5) ++tapCount;
    lastTapAt = now;
    tapDown = true;
  } else if (tapDown && value <= tapReleaseThreshold) {
    tapDown = false;
  }
  if (tapCount && !tapDown && now - lastTapAt >= tapGapMs) {
    if (tapCount >= 2 && tapCount <= 4) {
      eventTapCount = tapCount;
      ++eventId;
      updateOled();
    }
    tapCount = 0;
  }
}

bool parseSensorSample(const char *line, long &a0) {
  while (*line) {
    const char *end = strchr(line, ',');
    const size_t length = end ? static_cast<size_t>(end - line) : strlen(line);
    const char *separator = static_cast<const char *>(memchr(line, ':', length));
    if (separator && separator - line == 7 && memcmp(line, "Pad1_A0", 7) == 0) {
      const char *digit = separator + 1;
      if (digit == line + length) return false;
      long parsed = 0;
      while (digit < line + length) {
        if (*digit < '0' || *digit > '9') return false;
        const int next = *digit++ - '0';
        if (parsed > (LONG_MAX - next) / 10) return false;
        parsed = parsed * 10 + next;
      }
      a0 = parsed;
      return true;
    }
    if (!end) break;
    line = end + 1;
  }
  return false;
}

void handleData() {
  if (!hasSample) {
    server.send(503, "application/json", "{\"error\":\"waiting_for_nano\"}");
    return;
  }
  char json[64];
  snprintf(json, sizeof(json), "{\"a0\":%ld,\"pressed\":%s}", latestA0, latestA0 >= tapPressThreshold ? "true" : "false");
  server.send(200, "application/json", json);
}

void handleSerial() {
  while (nanoSerial.available()) {
    const char c = static_cast<char>(nanoSerial.read());
    if (c == '\n') {
      if (!discardingLine) {
        lineBuffer[lineLength] = '\0';
        long a0;
        if (parseSensorSample(lineBuffer, a0)) {
          hasSample = true;
          latestA0 = a0;
        }
      }
      lineLength = 0;
      discardingLine = false;
    } else if (!discardingLine) {
      if (lineLength + 1 < lineCapacity) lineBuffer[lineLength++] = c;
      else { lineLength = 0; discardingLine = true; }
    }
  }
}

void setup() {
  Serial.begin(115200);
  nanoSerial.begin(115200);
  oled.begin();
  updateOled();
  WiFi.mode(WIFI_AP);
  WiFi.softAP(apSsid, apPassword);
  server.on("/", HTTP_GET, []() { server.send_P(200, "text/html", page); });
  server.on("/data", HTTP_GET, handleData);
  server.begin();
}

void loop() {
  handleSerial();
  if (millis() - lastOledAt >= 1000) {
    lastOledAt = millis();
    updateOled();
  }
  server.handleClient();
}
