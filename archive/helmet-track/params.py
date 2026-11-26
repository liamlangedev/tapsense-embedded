"""Shared parameters for the helmet impact sensing prototype.

Everything the device, the gateway and the UI agree on lives here.
Units: acceleration in g (1 g = 9.80665 m/s^2) as reported by a shell-bonded
accelerometer per zone.
"""

FS = 8000  # Hz per zone, shock-grade sampling
# Zone layout, clockwise seen from above, T = crown.
ZONES = ["F", "FR", "R", "BR", "BL", "L", "FL", "T"]
ZONE_IDX = {z: i for i, z in enumerate(ZONES)}
NZONES = len(ZONES)

# Adjacency (used for spatial plausibility, not for detection).
ADJ = {
    "F": {"FR", "FL", "T"},
    "FR": {"F", "R", "T"},
    "R": {"FR", "BR", "T"},
    "BR": {"R", "BL", "T"},
    "BL": {"BR", "L", "T"},
    "L": {"BL", "FL", "T"},
    "FL": {"L", "F", "T"},
    "T": set(ZONES) - {"T"},
}

# Detector
WIN_MS = 50           # candidate window
HOP_MS = 10           # analysis hop
PRE_MS = 200          # evidence window before trigger
POST_MS = 300         # evidence window after trigger
QUIET_MS = 50         # event closed after this much sub-threshold
ABS_FLOOR_G = 4.0     # never trigger below this, regardless of noise
K_MAD = 6.0           # adaptive threshold = median + K_MAD * MAD
REPORT_GRADE = 2      # grade >= this is a reportable hit event

# Alert frame / transport
VER = 1
SIG_BYTES = 64        # Ed25519
MAX_LORA_BYTES = 222  # SX127x SF9/125k payload budget we design against

CLASSES = [
    "informational",   # 0 low energy contact, kept as evidence, not an alarm
    "sensor_fault",    # 1 detached/loose sensor, saturation, mains hum
    "blunt_impact",    # 2 doorframe, weapon butt, vehicle bounce
    "fragment_hit",    # 3 small high-velocity fragment
    "blast",           # 4 overpressure / large multi-zone event
]
CLASS_ID = {c: i for i, c in enumerate(CLASSES)}

GRADES = ["info", "minor", "moderate", "severe", "critical"]

# Evidence bundle
EVIDENCE_VERSION = 1