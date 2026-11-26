# Archive — helmet impact track

**This is not part of TapSense.** It is the first approach we explored at the same
hackathon, kept here for reference and because it shares the same sensor technology.

## What it was

The EDTH venue ran several sponsored challenges. Challenge 4 (CurveSYS) asked for a
smart helmet: detect impacts across up to eight force-sensor zones, classify the
event on the edge, and emit small, integrity-protected alerts to a squad-leader
dashboard over BLE → gateway, with offline store-and-forward.

The design work is real — a signal simulator, a detector, a feature-based
classifier, a 146-byte event frame with an Ed25519 signature and a hash chain.
Most of it was written but never run against the real evaluation dataset.

## Why it stopped

The team pivoted to **TapSense** — the same CurveSYS force sensors, but used as a
gesture interface on gear instead of an impact detector in a helmet. Tactical
medical resupply was the demo, it fit the time we had, and it was a better story.

## Files

| File | What |
|---|---|
| `params.py` | Sensor and detector constants |
| `signalgen.py` | Synthetic 8-zone impact traces with ground truth |
| `detector.py` | Windowed onset/feature detector, classes event candidates |
| `frame.py` | Event frame codec — signing, hash chain, commit/reveal |
| `helmet_simulator.py` | Drives the pipeline end to end from generated traces |
| `helmet_edge_firmware.ino` | Edge firmware sketch for the helmet variant |
| `ESP32_current_monitor_README.md` | Wiring/README from the ESP32 current-sense side experiment |
| `QUICK_TEST.txt` | GPIO34 bring-up checklist (German) |

## Status

Treat all of this as **unverified**. It parsed and was reviewed, but the detector and
frame code were never exercised against the hidden evaluation set, and the numbers in
the original plan document were partly retracted for being invented. There is no
`PLAN.md`/`HANDOFF.md` here on purpose — those described an architecture that was
explicitly abandoned, and copying them would suggest it worked.

The reusable, useful part is the signal-processing structure in `signalgen.py` and
`detector.py`, if you ever want to revisit force-based event detection.
