#!/usr/bin/env python3
"""Generate the TapSense v2 (4-Zone Helmet + Plate Carrier) architecture & wiring SVG.

    python3 tools/gen_schematic_v2.py

Outputs:
    docs/wiring/tapsense-helmet-plate.svg
    docs/wiring/tapsense-helmet-plate.html
"""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "wiring"

W, H = 1360, 820
parts = []


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def text(x, y, s, cls="label", anchor="start"):
    parts.append(f'<text class="{cls}" x="{x}" y="{y}" text-anchor="{anchor}">{esc(s)}</text>')


def rect(x, y, w, h, cls="box", rx=12):
    parts.append(f'<rect class="{cls}" x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}"/>')


def wire(*pts, cls="wire"):
    d = " ".join(f"{'M' if i == 0 else 'L'}{px} {py}" for i, (px, py) in enumerate(pts))
    parts.append(f'<path class="{cls}" d="{d}"/>')


def dot(x, y, cls="node"):
    parts.append(f'<circle class="{cls}" cx="{x}" cy="{y}" r="4.5"/>')


def arrow_right(x1, x2, y, cls="wire"):
    wire((x1, y), (x2 - 8, y), cls=cls)
    parts.append(f'<path class="arrowhead" d="M{x2} {y} l-11 -6 v12 z"/>')


def render():
    # Title
    text(52, 54, "TapSense v2 — 4-Zone Directional Helmet + Plate Carrier Architecture", "lgtitle")
    text(52, 78, "Target architecture: directional impact vectoring + gesture-triggered drone dispatch", "sub")

    # 1) Helmet 4-Zone Ring (left top)
    HCX, HCY, HR = 185, 272, 76
    rect(48, 110, 275, 325, "card", 14)
    text(185, 138, "4-Zone Helmet Array", "title", "middle")
    text(185, 158, "CurveSYS FSR · 10 kΩ divider each", "sub", "middle")

    parts.append(f'<circle cx="{HCX}" cy="{HCY}" r="{HR}" fill="#0b121c" stroke="#475569" stroke-width="2.5"/>')
    parts.append(f'<circle cx="{HCX}" cy="{HCY}" r="30" fill="#16202e" stroke="#334155" stroke-width="1.5" stroke-dasharray="4 4"/>')
    text(HCX, HCY + 4, "atan2(x,y)", "monosmall", "middle")

    # 4 sensor pads on helmet
    pads = [
        (HCX, HCY - HR, "H_N (0°)", "A0"),
        (HCX + HR, HCY, "H_E (90°)", "A1"),
        (HCX, HCY + HR, "H_S (180°)", "A2"),
        (HCX - HR, HCY, "H_W (270°)", "A3"),
    ]
    for px, py, lbl, pin in pads:
        parts.append(f'<rect x="{px - 22}" y="{py - 12}" width="44" height="24" rx="5" fill="#1f2f42" stroke="#fbbf24" stroke-width="2"/>')
        text(px, py + 4, pin, "plabel", "middle")

    text(HCX, HCY - HR - 16, "Front · H_N (0°)", "netsmall", "middle")
    text(HCX, HCY + HR + 26, "Back · H_S (180°)", "netsmall", "middle")
    text(HCX - HR - 26, HCY + 4, "L · W", "netsmall", "end")
    text(HCX + HR + 26, HCY + 4, "R · E", "netsmall", "start")

    text(185, 415, "Vector sum: dx = E-W, dy = N-S", "mono", "middle")

    # 2) Plate Carrier Tap Pad (left bottom)
    rect(48, 460, 275, 185, "card", 14)
    text(185, 492, "Plate Carrier Tap Pad", "title", "middle")
    text(185, 514, "Chest / shoulder gesture trigger", "sub", "middle")
    rect(125, 534, 120, 44, "res", 8)
    text(185, 561, "P_TAP → A4", "plabel", "middle")
    text(185, 604, "2 taps : critical_situation", "mono", "middle")
    text(185, 624, "3 taps : medical_supply_drone", "mono", "middle")

    # 3) Arduino Nano (middle-left)
    NX, NY, NW, NH = 415, 165, 220, 425
    rect(NX, NY, NW, NH, "box", 14)
    text(NX + NW / 2, NY + 34, "Arduino Nano", "title", "middle")
    text(NX + NW / 2, NY + 56, "100 Hz · 5-ch ADC", "sub", "middle")

    nano_pins = [
        (255, "A0  H_N"),
        (295, "A1  H_E"),
        (335, "A2  H_S"),
        (375, "A3  H_W"),
        (555, "A4  P_TAP"),
    ]
    for py, pl in nano_pins:
        dot(NX, py, "pinpt")
        text(NX + 14, py + 5, pl, "pin")

    # Connect Helmet -> Nano A0..A3
    for py in (255, 295, 335, 375):
        wire((323, py), (NX, py))
    # Connect Plate -> Nano A4
    wire((323, 555), (NX, 555))

    text(NX + NW / 2, NY + 275, "CSV @ 115200 baud:", "sub", "middle")
    text(NX + NW / 2, NY + 297, "H_N:..,H_E:..,H_S:..,", "mono", "middle")
    text(NX + NW / 2, NY + 315, "H_W:..,P_TAP:..", "mono", "middle")

    # 4) Voltage Divider + ESP8266 Hub (middle-right)
    EX, EY, EW, EH = 745, 175, 265, 430
    TX_Y = 390
    dot(NX + NW, TX_Y, "pinpt")
    text(NX + NW - 12, TX_Y + 5, "D1/TX", "pin", "end")

    wire((NX + NW, TX_Y), (665, TX_Y))
    rect(665, TX_Y - 14, 48, 28, "res", 4)
    text(689, TX_Y - 22, "1 kΩ", "plabel", "middle")
    wire((713, TX_Y), (EX, TX_Y))
    dot(727, TX_Y)
    wire((727, TX_Y), (727, 455))
    rect(713, 455, 28, 56, "res", 4)
    text(705, 488, "2 kΩ", "plabel", "end")
    wire((727, 511), (727, 555), cls="gnd")
    text(727, 574, "GND", "netsmall", "middle")

    rect(EX, EY, EW, EH, "box", 14)
    text(EX + EW / 2, EY + 34, "ESP8266 Hub v2", "title", "middle")
    text(EX + EW / 2, EY + 56, "AP: FSR-Hub (192.168.4.1)", "sub", "middle")
    dot(EX, TX_Y, "pinpt")
    text(EX - 8, TX_Y - 12, "D7", "pin", "end")

    # Internal ESP modules
    rect(EX + 18, EY + 82, EW - 36, 80, "inner", 8)
    text(EX + EW / 2, EY + 106, "Directional Impact Engine", "label", "middle")
    text(EX + EW / 2, EY + 126, "EMA baseline + vector deg", "monosmall", "middle")
    text(EX + EW / 2, EY + 144, "severity + confidence", "monosmall", "middle")

    rect(EX + 18, EY + 178, EW - 36, 72, "inner", 8)
    text(EX + EW / 2, EY + 202, "Plate Gesture Classifier", "label", "middle")
    text(EX + EW / 2, EY + 222, "attaches last helmet impact", "monosmall", "middle")

    rect(EX + 18, EY + 266, EW - 36, 76, "inner", 8)
    text(EX + EW / 2, EY + 290, "16-Event Ring Buffer", "label", "middle")
    text(EX + EW / 2, EY + 310, "GET /events?since=<id>", "monosmall", "middle")
    text(EX + EW / 2, EY + 328, "GET /data  |  GET / + OLED", "monosmall", "middle")

    text(EX + EW / 2, EY + 395, "Store-and-Forward over Wi-Fi", "netsmall", "middle")

    # 5) Raspberry Pi + Drone Dispatch (right)
    PX, PY, PW, PH = 1095, 175, 225, 195
    rect(PX, PY, PW, PH, "usb", 14)
    text(PX + PW / 2, PY + 34, "Raspberry Pi", "title", "middle")
    text(PX + PW / 2, PY + 56, "tapsense_pi_client.py", "monosmall", "middle")
    text(PX + PW / 2, PY + 96, "• polls /events?since=id", "mono", "middle")
    text(PX + PW / 2, PY + 118, "• logs JSONL locally", "mono", "middle")
    text(PX + PW / 2, PY + 140, "• feeds C2 / dashboard", "mono", "middle")
    text(PX + PW / 2, PY + 162, "• triggers drone webhook", "mono", "middle")

    arrow_right(EX + EW, PX, 272)
    text(1052, 256, "Wi-Fi", "netsmall", "middle")

    DX, DY, DW, DH = 1095, 430, 225, 175
    rect(DX, DY, DW, DH, "card", 14)
    text(DX + DW / 2, DY + 36, "Autonomous Drone", "title", "middle")
    text(DX + DW / 2, DY + 58, "Medical Resupply / Medevac", "sub", "middle")
    text(DX + DW / 2, DY + 98, "mission_type + GPS", "mono", "middle")
    text(DX + DW / 2, DY + 120, "+ helmet_impact:", "mono", "middle")
    text(DX + DW / 2, DY + 142, "direction_deg, severity", "monosmall", "middle")

    wire((PX + PW / 2, PY + PH), (PX + PW / 2, DY - 8))
    parts.append(f'<path class="arrowhead" d="M{PX + PW / 2} {DY} l-6 -11 h12 z"/>')
    text(PX + PW / 2 + 12, 405, "HTTP POST", "netsmall")

    # Footer note
    rect(48, 690, 1272, 76, "legendbox", 10)
    text(72, 720, "How the two subsystems combine:", "label")
    text(72, 745, "A helmet hit is detected and stored with its impact angle (0–359°). When the operator later taps 3× on the plate carrier, the gesture event automatically attaches that impact vector for medevac / drone triage.", "sub")

    css = """
svg{font-family:ui-sans-serif,system-ui,sans-serif}
.box{fill:#16202e;stroke:#7d93ab;stroke-width:2}
.card{fill:#131c28;stroke:#4b5f75;stroke-width:2}
.inner{fill:#0d1520;stroke:#3b4c61;stroke-width:1.5;stroke-dasharray:5 4}
.usb{fill:#13251b;stroke:#4f9464;stroke-width:2}
.wire{fill:none;stroke:#38bdf8;stroke-width:3;stroke-linejoin:round;stroke-linecap:round}
.gnd{fill:none;stroke:#a78bfa;stroke-width:3;stroke-linecap:round}
.res{fill:#1f2f42;stroke:#fbbf24;stroke-width:2}
.arrowhead{fill:#38bdf8;stroke:none}
.node{fill:#38bdf8;stroke:none}
.pinpt{fill:#cbd5e1;stroke:none}
.legendbox{fill:#101824;stroke:#334155;stroke-width:1.5}
.title{fill:#f8fafc;font:700 17px ui-sans-serif,system-ui}
.sub{fill:#94a3b8;font:12.5px ui-sans-serif,system-ui}
.pin{fill:#dbe6f1;font:13px ui-monospace,monospace}
.mono{fill:#cbd5e1;font:12px ui-monospace,monospace}
.monosmall{fill:#7dd3fc;font:11.5px ui-monospace,monospace}
.label{fill:#f1f5f9;font:600 13.5px ui-sans-serif,system-ui}
.plabel{fill:#fcd34d;font:600 12px ui-monospace,monospace}
.netsmall{fill:#7dd3fc;font:11.5px ui-monospace,monospace}
.lgtitle{fill:#f8fafc;font:700 19px ui-sans-serif,system-ui}
"""
    body = "\n".join(parts)
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
        f'width="{W}" height="{H}" role="img" '
        f'aria-label="TapSense v2 target architecture: 4-zone directional helmet and plate carrier tap pad">\n'
        f"<style>{css}</style>\n"
        f'<rect x="0" y="0" width="{W}" height="{H}" fill="#0d1117"/>\n'
        f"{body}\n</svg>\n"
    )
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "tapsense-helmet-plate.svg").write_text(svg, encoding="utf-8")

    html = """<!doctype html>
<html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>TapSense v2 — 4-Zone Helmet &amp; Plate Architecture</title>
<style>
  :root{color-scheme:dark}
  body{background:#0d1117;color:#e5e7eb;font:16px/1.6 ui-sans-serif,system-ui,sans-serif;
       max-width:1380px;margin:28px auto;padding:0 18px}
  img{width:100%;height:auto;border:1px solid #334155;border-radius:12px}
  code{font-family:ui-monospace,monospace;color:#7dd3fc}
</style>
<h1>TapSense v2 — 4-Zone Helmet &amp; Plate Carrier</h1>
<p>Generated by <code>tools/gen_schematic_v2.py</code>.</p>
<img src="tapsense-helmet-plate.svg" alt="TapSense v2 target architecture">
</html>
"""
    (OUT / "tapsense-helmet-plate.html").write_text(html, encoding="utf-8")
    print(f"wrote {OUT / 'tapsense-helmet-plate.svg'}")


if __name__ == "__main__":
    render()
