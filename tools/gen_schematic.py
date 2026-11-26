#!/usr/bin/env python3
"""Generate the TapSense system schematic as standalone SVG + HTML wrapper.

Everything is computed, so the drawing can be regenerated after a wiring change:

    python3 tools/gen_schematic.py

Outputs (relative to the repo root):
    docs/wiring/tapsense-system.svg
    docs/wiring/tapsense-system.html

Layout notes
------------
Three FSR dividers are stacked in staggered columns so that each tap wire runs
horizontally into its own analog pin. Where a tap wire crosses a neighbouring
column's supply stub, the tap is drawn with a hop so the crossing is unambiguous.
"""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "wiring"

W, H = 1320, 1010
parts = []

GND_Y = 900
BUS_Y = 170

NANO_X, NANO_Y, NANO_W, NANO_H = 520, 200, 260, 440
ESP_X, ESP_Y, ESP_W, ESP_H = 1060, 200, 232, 440

COL_X = (175, 300, 425)
PIN_Y = (290, 425, 560)          # tap height == Nano analog pin height
NODE_X = 960
TX_Y = 470


# ----------------------------------------------------------------- helpers
def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def text(x, y, s, cls="label", anchor="start"):
    parts.append(f'<text class="{cls}" x="{x}" y="{y}" text-anchor="{anchor}">{esc(s)}</text>')


def wire(*pts, cls="wire"):
    d = " ".join(f"{'M' if i == 0 else 'L'}{px} {py}" for i, (px, py) in enumerate(pts))
    parts.append(f'<path class="{cls}" d="{d}"/>')


def wire_hop(x1, x2, y, hops=(), r=9):
    """Horizontal wire from x1 to x2 with semicircular jumps over `hops`."""
    d = [f"M{x1} {y}"]
    for hx in sorted(hops):
        d.append(f"L{hx - r} {y}A{r} {r} 0 0 1 {hx + r} {y}")
    d.append(f"L{x2} {y}")
    parts.append(f'<path class="wire" d="{"".join(d)}"/>')


def rect(x, y, w, h, cls="box", rx=None):
    r = f' rx="{rx}"' if rx else ""
    parts.append(f'<rect class="{cls}" x="{x}" y="{y}" width="{w}" height="{h}"{r}/>')


def res_h(cx, cy, w=100, h=36, label=None):
    rect(cx - w / 2, cy - h / 2, w, h, "res", 4)
    if label:
        text(cx, cy - h / 2 - 10, label, "plabel", "middle")


def res_v(cx, cy, w=34, h=96, label=None):
    rect(cx - w / 2, cy - h / 2, w, h, "res", 4)
    if label:
        text(cx + w / 2 + 10, cy + 5, label, "plabel", "start")


def fsr_v(cx, cy, w=34, h=64, label="FSR"):
    """Force-sensing resistor, vertical: box with a diagonal arrow through it."""
    x0, y0 = cx - w / 2, cy - h / 2
    rect(x0, y0, w, h, "res", 4)
    parts.append(
        f'<path class="arrow" d="M{x0 - 12} {y0 + h - 6} L{x0 + w + 12} {y0 + 6}"/>'
        f'<path class="arrowhead" d="M{x0 + w + 12} {y0 + 6} l-12 -1 l3 11 z"/>'
    )
    if label:
        text(cx, y0 - 12, label, "plabel", "middle")


def gnd(x, y):
    parts.append(
        f'<path class="gndsym" d="M{x - 14} {y} H{x + 14} M{x - 9} {y + 8} H{x + 9} '
        f'M{x - 4} {y + 16} H{x + 4}"/>'
    )


def dot(x, y, cls="node"):
    parts.append(f'<circle class="{cls}" cx="{x}" cy="{y}" r="5"/>')


def block(x, y, w, h, title, sub=None):
    rect(x, y, w, h, "box", 14)
    text(x + w / 2, y + 32, title, "title", "middle")
    if sub:
        text(x + w / 2, y + 56, sub, "sub", "middle")


def usb_box(cx, cy, label):
    rect(cx - 96, cy - 22, 192, 44, "usb", 8)
    text(cx, cy + 6, label, "usblabel", "middle")


def pinpt(x, y):
    parts.append(f'<circle class="pinpt" cx="{x}" cy="{y}" r="4"/>')


# ----------------------------------------------------------------- title
text(64, 58, "TapSense — sensing & embedded link", "lgtitle")
text(64, 80, "Nano → 1 kΩ/2 kΩ divider → ESP8266 access point", "sub")

# ----------------------------------------------------------------- power
usb_box(300, 122, "USB 5 V — Nano")
wire((300, 144), (300, BUS_Y))
wire((100, BUS_Y), (660, BUS_Y))          # 5 V bus
for i, x in enumerate(COL_X):              # supply stub down into each FSR
    wire((x, BUS_Y), (x, PIN_Y[i] - 102))
dot(300, BUS_Y)
wire((640, BUS_Y), (640, NANO_Y))
dot(640, BUS_Y)

# ----------------------------------------------------------------- FSR dividers
labels = ("Pad 1", "Pad 2", "Pad 3")
for i, cx in enumerate(COL_X):
    y_t = PIN_Y[i] - 110          # FSR top
    fsr_v(cx, y_t + 40, label=None)
    wire((cx, y_t + 72), (cx, PIN_Y[i]))
    dot(cx, PIN_Y[i])
    res_v(cx, PIN_Y[i] + 70, label="10 kΩ")
    wire((cx, PIN_Y[i] + 118), (cx, GND_Y))
    # tap into the Nano — hop over the other columns' supply stubs
    hops = [OTHER for OTHER in COL_X if OTHER > cx]
    wire_hop(cx, NANO_X, PIN_Y[i], hops)
    text(cx + 40, y_t + 45, "FSR", "plabel", "start")
    text(cx + 46, PIN_Y[i] - 9, labels[i], "netsmall")

# ----------------------------------------------------------------- Nano
block(NANO_X, NANO_Y, NANO_W, NANO_H, "Arduino Nano",
      "ATmega328P · 3-zone readout")
for i, y in enumerate(PIN_Y):
    pinpt(NANO_X, y)
    text(NANO_X + 14, y + 5, f"A{i}", "pin")
    text(NANO_X + 44, y + 5, f"({labels[i].split(' / ')[0]})", "monosmall")

pinpt(640, NANO_Y)
text(656, NANO_Y - 10, "5V", "pin")
pinpt(640, NANO_Y + NANO_H)
text(656, NANO_Y + NANO_H + 26, "GND", "pin")
wire((640, NANO_Y + NANO_H), (640, GND_Y))
dot(640, GND_Y)

pinpt(NANO_X + NANO_W, TX_Y)
text(NANO_X + NANO_W - 14, TX_Y - 10, "D1 / TX", "pin", "end")
wire((NANO_X + NANO_W, TX_Y), (820, TX_Y))

text(NANO_X + NANO_W / 2, NANO_Y + 396, "50 Hz · labelled CSV", "sub", "middle")
text(NANO_X + NANO_W / 2, NANO_Y + 418, "Pad1_A0:512,…", "mono", "middle")

# ----------------------------------------------------------------- divider
res_h(870, TX_Y, 100, 36, "1 kΩ")
wire((920, TX_Y), (NODE_X, TX_Y))
dot(NODE_X, TX_Y)
res_v(NODE_X, TX_Y + 80, label="2 kΩ")
wire((NODE_X, TX_Y), (NODE_X, TX_Y + 32))
wire((NODE_X, TX_Y + 128), (NODE_X, GND_Y))
dot(NODE_X, GND_Y)
wire((NODE_X, TX_Y), (ESP_X, TX_Y))

text(788, TX_Y - 14, "5 V", "netsmall")
text(1002, TX_Y + 24, "≈ 3.3 V", "netsmall")

# ----------------------------------------------------------------- ESP8266
block(ESP_X, ESP_Y, ESP_W, ESP_H, "ESP8266", "FSR-Hub access point")
pinpt(ESP_X, TX_Y)
text(ESP_X - 16, TX_Y - 34, "D7 / GPIO13 RX", "pin", "end")

usb_box(1170, 122, "USB 5 V — ESP")
wire((1170, 144), (1170, ESP_Y))
pinpt(1170, ESP_Y)
text(1188, ESP_Y - 10, "VIN", "pin", "start")
pinpt(1170, ESP_Y + ESP_H)
text(1188, ESP_Y + ESP_H + 26, "GND", "pin", "start")
wire((1170, ESP_Y + ESP_H), (1170, GND_Y))
dot(1170, GND_Y)

rect(ESP_X + 18, ESP_Y + 240, ESP_W - 36, 168, "inner", 10)
text(ESP_X + ESP_W / 2, ESP_Y + 266, "on-board SSD1306", "sub", "middle")
text(ESP_X + ESP_W / 2, ESP_Y + 288, "SCL = D5 / GPIO14", "monosmall", "middle")
text(ESP_X + ESP_W / 2, ESP_Y + 306, "SDA = D6 / GPIO12", "monosmall", "middle")
text(ESP_X + ESP_W / 2, ESP_Y + 338, "SSID  FSR-Hub", "monosmall", "middle")
text(ESP_X + ESP_W / 2, ESP_Y + 356, "fsr-sensor", "monosmall", "middle")
text(ESP_X + ESP_W / 2, ESP_Y + 382, "http://192.168.4.1", "monosmall", "middle")

# ----------------------------------------------------------------- ground
wire((80, GND_Y), (1270, GND_Y), cls="gnd")
for x in (175, 425, 640, 960, 1270):
    gnd(x, GND_Y)
text(100, GND_Y + 44, "COMMON GROUND — Nano GND ↔ ESP GND", "netsmall")

# ----------------------------------------------------------------- legend
def legend(x, y, glyph, label):
    if glyph == "wire":
        parts.append(f'<path class="wire" d="M{x} {y} H{x + 46}"/>')
    elif glyph == "hop":
        parts.append(f'<path class="wire" d="M{x} {y} L{x + 17} {y}A9 9 0 0 1 {x + 35} {y}L{x + 46} {y}"/>')
    elif glyph == "res":
        rect(x + 4, y - 11, 40, 22, "res", 3)
    elif glyph == "gnd":
        gnd(x + 22, y - 6)
    elif glyph == "fsr":
        rect(x + 4, y - 11, 40, 22, "res", 3)
        parts.append(f'<path class="arrow" d="M{x - 6} {y + 12} L{x + 54} {y - 14}"/>')
    text(x + 58, y + 5, label, "legend")


legend(100, 982, "wire", "signal")
legend(360, 982, "hop", "crossing — not connected")
legend(700, 982, "res", "resistor")
legend(940, 982, "gnd", "ground")
legend(1140, 982, "fsr", "force sensor")


def render():
    css = """
svg{font-family:ui-sans-serif,system-ui,sans-serif}
.box{fill:#16202e;stroke:#7d93ab;stroke-width:2}
.inner{fill:#0e1723;stroke:#4b5f75;stroke-width:1.5;stroke-dasharray:6 5}
.usb{fill:#1b2a1c;stroke:#5f9e63;stroke-width:2}
.usblabel{fill:#b6e3b8;font:600 15px ui-sans-serif,system-ui}
.wire{fill:none;stroke:#38bdf8;stroke-width:3.5;stroke-linejoin:round;stroke-linecap:round}
.gnd{fill:none;stroke:#a78bfa;stroke-width:3.5;stroke-linecap:round}
.gndsym{fill:none;stroke:#a78bfa;stroke-width:3;stroke-linecap:round}
.res{fill:#1f2f42;stroke:#fbbf24;stroke-width:2.5}
.arrow{fill:none;stroke:#fbbf24;stroke-width:2;stroke-linecap:round}
.arrowhead{fill:#fbbf24;stroke:none}
.node{fill:#38bdf8;stroke:none}
.pinpt{fill:#cbd5e1;stroke:none}
.pinframe{stroke:#64748b;stroke-width:1.5;stroke-dasharray:3 3}
.legendbox{fill:#101a26;stroke:#3b4c61;stroke-width:1.5}
.title{fill:#f8fafc;font:700 19px ui-sans-serif,system-ui}
.sub{fill:#93a7bc;font:13px ui-sans-serif,system-ui}
.pin{fill:#dbe6f1;font:14px ui-monospace,SFMono-Regular,monospace}
.mono{fill:#8fb3d0;font:11.5px ui-monospace,monospace}
.monosmall{fill:#8fb3d0;font:11px ui-monospace,monospace}
.label{fill:#e2e8f0;font:14px ui-sans-serif,system-ui}
.plabel{fill:#fcd34d;font:600 13px ui-monospace,monospace}
.netsmall{fill:#7dd3fc;font:12px ui-monospace,monospace}
.lgtitle{fill:#f8fafc;font:700 18px ui-sans-serif,system-ui}
.lgtitle2{fill:#8fa3b8;font:600 11px ui-sans-serif,system-ui;letter-spacing:.12em}
.legend{fill:#cbd5e1;font:13px ui-sans-serif,system-ui}
"""
    body = "\n".join(parts)
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
        f'width="{W}" height="{H}" role="img" '
        f'aria-label="TapSense system schematic: three FSR dividers into an Arduino Nano, '
        f'Nano TX through a 1k/2k resistor divider into an ESP8266 access point, '
        f'with a common ground rail">\n'
        f"<style>{css}</style>\n"
        f'<rect x="0" y="0" width="{W}" height="{H}" fill="#0d1117"/>\n'
        f"{body}\n</svg>\n"
    )
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "tapsense-system.svg").write_text(svg, encoding="utf-8")

    html = f"""<!doctype html>
<html lang="en">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>TapSense — system schematic</title>
<style>
  :root{{color-scheme:dark}}
  body{{background:#0d1117;color:#e5e7eb;font:16px/1.6 ui-sans-serif,system-ui,sans-serif;
       max-width:1340px;margin:28px auto;padding:0 18px}}
  h1{{font-size:1.45rem;margin:0 0 6px}}
  h2{{font-size:1.05rem;margin:26px 0 8px;color:#dbe6f1}}
  p{{color:#c3cfdd;margin:0 0 18px}}
  img{{width:100%;height:auto;border:1px solid #334155;border-radius:12px;background:#0d1117}}
  table{{border-collapse:collapse;margin:16px 0;font-size:.92rem}}
  th,td{{border:1px solid #334155;padding:7px 12px;text-align:left}}
  th{{background:#16202e;color:#e2e8f0}}
  code{{font-family:ui-monospace,monospace;color:#7dd3fc}}
  ul{{color:#c3cfdd}}
  .warn{{border-left:3px solid #fbbf24;padding:2px 0 2px 14px;margin:16px 0;color:#e8d5a0}}
</style>
<h1>TapSense — system schematic</h1>
<p>Generated by <code>tools/gen_schematic.py</code>. Do not edit the SVG by hand —
change the script and regenerate.</p>
<img src="tapsense-system.svg" alt="TapSense system schematic">

<h2>Nets</h2>
<table>
<tr><th>Net</th><th>From</th><th>To</th><th>Level</th></tr>
<tr><td>Pad1 / Pad2 / Pad3</td><td>FSR divider node</td><td>Nano A0 / A1 / A2</td><td>0–5 V analog</td></tr>
<tr><td>NANO_TX</td><td>Nano D1 / TX</td><td>1 kΩ → divider node</td><td>5 V logic</td></tr>
<tr><td>ESP_RX</td><td>divider node</td><td>ESP D7 / GPIO13</td><td>≈3.3 V</td></tr>
<tr><td>GND</td><td>Nano + ESP</td><td>common rail</td><td>—</td></tr>
</table>

<h2>Wiring notes</h2>
<ul>
  <li>Each FSR sits in a divider: <code>5 V → FSR → analog pin → 10 kΩ → GND</code>.</li>
  <li>The 1 kΩ / 2 kΩ network is <strong>not optional</strong> — the Nano drives 5 V, the ESP8266 RX pin is 3.3 V only.</li>
  <li>The ESP8266 TX pin stays disconnected; the serial link is one-way by design.</li>
  <li>Each board has its own USB supply. The grounds must still be tied together.</li>
  <li>The Ideaspark board carries the OLED on <code>D5</code> (SCL) and <code>D6</code> (SDA).</li>
  <li>A wire that hops another is <em>not</em> connected to it.</li>
</ul>

<div class="warn">Disconnect the Nano TX wire while flashing the ESP over USB — GPIO13 sits next to the
programmer path, and the divider fights the programmer.</div>
</html>
"""
    (OUT / "tapsense-system.html").write_text(html, encoding="utf-8")
    print(f"wrote {OUT / 'tapsense-system.svg'}")
    print(f"wrote {OUT / 'tapsense-system.html'}")


if __name__ == "__main__":
    render()