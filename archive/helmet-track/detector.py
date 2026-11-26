"""On-device multi-zone impact detector.

Design constraints that shaped this file:
  * it must run on an MCU: one 50 ms window per 10 ms hop, features only
  * it must be explainable: every alert carries the numbers that triggered it,
    so a commander or a court can read *why*, not just a neural net's opinion
  * it must never confuse real, non-reportable activity (helmet off, gear
    rattle, engine idle, a jittery individual) with a hit that matters

The detector only decides *candidate events*. Grading and the final
"reportable / not reportable" call happen on the same device, but the evidence
window is captured regardless so the call can be re-audited later.
"""

from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass, field

import numpy as np

from .params import (
    FS, HOP_MS, WIN_MS, PRE_MS, POST_MS, QUIET_MS, ABS_FLOOR_G, K_MAD,
    NZONES, ZONES, GRADES, CLASS_ID, EVIDENCE_VERSION,
)

HOP_N = FS * HOP_MS // 1000          # 80 samples
WIN_N = FS * WIN_MS // 1000          # 400 samples
PRE_N = FS * PRE_MS // 1000
POST_N = FS * POST_MS // 1000
QUIET_N = FS * QUIET_MS // 1000
HIST_MS = 1600
HIST_N = FS * HIST_MS // 1000
DECIM = 4                            # evidence is stored at 2 kHz
EV_FS = FS // DECIM


# ---------------------------------------------------------------------------
# Event record
# ---------------------------------------------------------------------------
@dataclass
class ImpactEvent:
    t_host_ms: int                  # timestamp of event onset (device clock)
    t_close_ms: int
    wav: np.ndarray                 # (n, 8) float32, raw evidence window
    wav_t0_ms: int
    peak_g: np.ndarray              # per zone
    nzones: int
    onset_ms: np.ndarray            # per zone onset offset (ms), inf if none
    features: dict
    cls: int
    grade: int
    conf: int
    explanations: list[str] = field(default_factory=list)

    # -- evidence commitment -------------------------------------------
    def evidence_bytes(self) -> bytes:
        """Canonical byte form of the evidence that will be revealed later."""
        d = self.wav[::DECIM]
        q = np.clip(np.round(d * 100), -32768, 32767).astype("<i2")
        hdr = struct.pack(
            "<BIIHBB8H",
            EVIDENCE_VERSION, self.wav_t0_ms & 0xFFFFFFFF, len(self.wav) * 1000 // FS,
            EV_FS, NZONES, self.cls,
            *[int(round(x * 10)) & 0xFFFF for x in self.peak_g],
        )
        return hdr + q.tobytes()

    def evidence_digest(self) -> bytes:
        return hashlib.sha256(self.evidence_bytes()).digest()

    @property
    def dur_ms(self) -> int:
        return len(self.wav) * 1000 // FS

    def to_dict(self) -> dict:
        return {
            "cls": self.cls,
            "class": _CLASS_NAME[self.cls],
            "grade": self.grade,
            "grade_name": GRADES[self.grade],
            "conf": self.conf,
            "t_host_ms": self.t_host_ms,
            "peak_g": {z: round(float(self.peak_g[i]), 1) for i, z in enumerate(ZONES)},
            "peak_max_g": round(float(self.peak_g.max()), 1),
            "nzones": int(self.nzones),
            "dur_ms": self.dur_ms,
            "features": {k: (round(v, 4) if isinstance(v, float) else v)
                         for k, v in self.features.items()},
            "explains": self.explanations,
            "evidence_digest": self.evidence_digest().hex(),
            "evidence_ms": self.dur_ms,
            "evidence_fs": EV_FS,
        }


_CLASS_NAME = ["informational", "sensor_fault", "blunt_impact", "fragment_hit", "blast"]


# ---------------------------------------------------------------------------
# Feature extraction over a captured evidence window
# ---------------------------------------------------------------------------
def _spectral(z: np.ndarray, fs: int = FS) -> tuple[float, float, float, float]:
    """(centroid Hz, flatness, hf_ratio, hum_ratio) for one zone window."""
    n = len(z)
    if n < 16:
        return 0.0, 0.0, 0.0, 0.0
    w = np.hanning(n).astype(np.float32)
    spec = np.abs(np.fft.rfft(z * w)) + 1e-12
    freqs = np.fft.rfftfreq(n, 1 / fs)
    p = spec ** 2
    tot = p.sum()
    centroid = float((freqs * p).sum() / tot)
    flatness = float(np.exp(np.log(spec).mean()) / spec.mean())
    hf = float(p[freqs > 800].sum() / tot)
    hum = float((p[(freqs > 45) & (freqs < 55)].sum()
                 + p[(freqs > 145) & (freqs < 155)].sum()) / tot)
    return centroid, flatness, hf, hum


def _onsets(wav: np.ndarray, thr: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Per-zone onset offset (ms) and peak (g) relative to window start."""
    above = np.abs(wav) > thr[None, :]
    nz = wav.shape[1]
    onset = np.full(nz, np.inf, dtype=np.float32)
    peak = np.abs(wav).max(axis=0)
    for i in range(nz):
        idx = np.flatnonzero(above[:, i])
        if idx.size:
            onset[i] = idx[0] * 1000.0 / FS
    return onset, peak


def extract_features(wav: np.ndarray) -> dict:
    thr = np.maximum(ABS_FLOOR_G, 0.25 * np.abs(wav).max(axis=0))
    onset, peak = _onsets(wav, thr)
    active = np.isfinite(onset)
    nz = int(active.sum())
    # Global onset = first zone to trigger.
    t0 = float(onset[active].min()) if nz else 0.0
    spread = float(onset[active].max() - onset[active].min()) if nz > 1 else 0.0
    zi = int(np.argmax(peak))
    z = wav[:, zi]
    pz = float(peak[zi])
    a = np.abs(z)
    # Rise: 10% -> 90% of that zone's peak after global onset.
    i0 = max(0, int(t0 * FS / 1000))
    seg = a[i0:]
    if seg.size and pz > 0:
        i10 = np.argmax(seg >= 0.1 * pz)
        i90 = np.argmax(seg >= 0.9 * pz)
        rise_us = int(max(0, (i90 - i10)) * 1e6 / FS)
    else:
        rise_us = 0
    # Duration above half peak in the strongest zone.
    half = np.flatnonzero(a >= 0.5 * pz)
    dur_ms = int((half[-1] - half[0]) * 1000 / FS) if half.size else 0
    centroid, flatness, hf, hum = _spectral(z)
    rms = float(np.sqrt(np.mean(seg ** 2))) if seg.size else 0.0
    crest = float(pz / rms) if rms > 1e-6 else 0.0
    # Impulse: integral of a^2 over the zone, g^2*s.
    impulse = float(np.sum(seg ** 2) / FS) if seg.size else 0.0
    # Multi-zone coherence: correlation of the two strongest zones' onsets.
    sim = spread  # ms between first and last zone onset
    return dict(
        peak_max_g=pz, nzones=nz, onset_spread_ms=sim, onset_ms=t0,
        rise_us=rise_us, dur_ms=dur_ms, centroid_hz=centroid, flatness=flatness,
        hf_ratio=hf, hum_ratio=hum, crest=crest, impulse_g2s=impulse,
        rms_g=rms, peak_zone=ZONES[zi],
        peaks={z: round(float(peak[i]), 1) for i, z in enumerate(ZONES)},
    )


# ---------------------------------------------------------------------------
# Classification: explicit rules, each one auditable
# ---------------------------------------------------------------------------
def classify(f: dict, event_ms: int) -> tuple[int, int, int, list[str]]:
    """Return (cls, grade, conf, explanations)."""
    exp: list[str] = []
    peak = f["peak_max_g"]
    nz = f["nzones"]
    rise = f["rise_us"]
    dur = f["dur_ms"]
    cen = f["centroid_hz"]
    hum = f["hum_ratio"]
    spread = f["onset_spread_ms"]

    # 1) Sensor fault: long, narrowband, one or two zones, non-physical.
    if hum > 0.30 and event_ms > 1500 and nz <= 2:
        exp.append(f"mains hum {hum:.0%} of energy over {event_ms} ms in {nz} zone(s) -> sensor fault, not a hit")
        return CLASS_ID["sensor_fault"], 0, 95, exp

    # 2) Blast: many zones load almost simultaneously, long low-frequency ramp.
    if nz >= 4 and spread <= 6.0 and peak >= 15.0:
        exp.append(f"{nz} zones triggered within {spread:.1f} ms -> simultaneous whole-shell load")
        exp.append(f"low spectral centroid {cen:.0f} Hz, {dur} ms envelope -> overpressure, not a single fragment")
        grade = 4 if peak >= 70 or f["impulse_g2s"] > 2.0 else (3 if peak >= 35 else 2)
        conf = int(min(98, 60 + 6 * nz + (20 if spread <= 3 else 0)))
        return CLASS_ID["blast"], grade, conf, exp

    # 3) Fragment hit: very fast rise, high frequency, localised, short ring.
    if rise <= 1500 and cen >= 600 and nz <= 3:
        exp.append(f"rise time {rise} us and centroid {cen:.0f} Hz -> high-velocity point load")
        exp.append(f"{nz}/8 zones above threshold -> localised, consistent with a fragment strike")
        grade = 4 if peak >= 55 else (3 if peak >= 25 else 2)
        conf = int(min(97, 55 + (20 if rise <= 700 else 8) + (12 if cen >= 900 else 0) + (8 if nz <= 2 else 0)))
        return CLASS_ID["fragment_hit"], grade, conf, exp

    # 4) Strong but slow and low-frequency: blunt trauma / vehicle / equipment.
    if peak >= 12.0 and cen < 600:
        exp.append(f"slow rise {rise} us, low centroid {cen:.0f} Hz -> blunt contact, not a fragment")
        grade = 3 if peak >= 35 else (2 if peak >= 20 else 1)
        conf = int(min(92, 50 + peak))
        return CLASS_ID["blunt_impact"], grade, conf, exp

    # 5) Anything else: real signal, not reportable.
    exp.append(f"peak {peak:.1f} g with rise {rise} us / centroid {cen:.0f} Hz below report criteria -> handling or noise")
    return CLASS_ID["informational"], 0, int(min(90, 40 + peak)), exp


# ---------------------------------------------------------------------------
# Streaming detector
# ---------------------------------------------------------------------------
class ImpactDetector:
    """Push blocks of (N, 8) samples, get ImpactEvents back."""

    def __init__(self, dev_id: str):
        self.dev_id = dev_id
        self.hist = np.zeros((HIST_N, NZONES), dtype=np.float32)
        self.hist_w = 0                       # absolute sample index of hist[-1]+1
        self.pending = np.zeros((0, NZONES), dtype=np.float32)
        self.peak_hist: list[float] = []
        self.n_samples = 0
        self.in_event = False
        self.ev_first_ms = 0
        self.ev_last_ms = 0
        self.quiet_since_ms: int | None = None
        self._n_events = 0

    # -- helpers --------------------------------------------------------
    @property
    def t_ms(self) -> int:
        return self.n_samples * 1000 // FS

    def _threshold(self) -> float:
        if len(self.peak_hist) < 40:
            return ABS_FLOOR_G
        a = np.asarray(self.peak_hist[-400:])
        med = float(np.median(a))
        mad = float(np.median(np.abs(a - med))) * 1.4826
        return max(ABS_FLOOR_G, med + K_MAD * mad)

    def _append_hist(self, block: np.ndarray) -> None:
        n = len(block)
        if n >= HIST_N:
            self.hist[:] = block[-HIST_N:]
            self.hist_w = self.n_samples + n
            return
        self.hist[:-n] = self.hist[n:]
        self.hist[-n:] = block
        self.hist_w = self.n_samples + n

    def _window(self, t_ms: int) -> np.ndarray:
        """Raw samples for [t_ms, t_ms + HIST_MS) if still in the buffer."""
        start = int(t_ms * FS / 1000)
        off = start - (self.hist_w - HIST_N)
        off = max(0, min(HIST_N, off))
        return self.hist[off:]

    # -- main -----------------------------------------------------------
    def process(self, block: np.ndarray) -> list[ImpactEvent]:
        out: list[ImpactEvent] = []
        self.pending = np.concatenate([self.pending, block.astype(np.float32)], axis=0) \
            if len(self.pending) else block.astype(np.float32).copy()

        while len(self.pending) >= HOP_N:
            hop = self.pending[:HOP_N]
            self.pending = self.pending[HOP_N:]
            self._append_hist(hop)
            self.n_samples += HOP_N
            now_ms = self.t_ms

            win = self.hist[-WIN_N:]
            pk = float(np.abs(win).max())
            thr = self._threshold()
            triggered = pk > thr
            if not self.in_event:
                self.peak_hist.append(pk)
                if len(self.peak_hist) > 2000:
                    self.peak_hist = self.peak_hist[-2000:]
            if triggered:
                if not self.in_event:
                    self.in_event = True
                    self.ev_first_ms = max(0, now_ms - WIN_MS)
                    self._n_events += 1
                self.ev_last_ms = now_ms
                self.quiet_since_ms = None
            elif self.in_event:
                # Close the event once it has been quiet long enough.
                if now_ms - self.ev_last_ms >= POST_MS:
                    ev = self._close(now_ms)
                    if ev is not None:
                        out.append(ev)
        return out

    def _close(self, now_ms: int) -> ImpactEvent | None:
        t0 = max(0, self.ev_first_ms - PRE_MS)
        t1 = self.ev_last_ms + POST_MS
        wav = self._window(t0).copy()
        # Bound evidence to what the ring buffer still holds.
        avail_ms = len(wav) * 1000 // FS
        t1 = min(t1, t0 + avail_ms)
        n = max(1, (t1 - t0) * FS // 1000)
        wav = wav[:n]
        event_ms = self.ev_last_ms - self.ev_first_ms
        self.in_event = False
        if wav.shape[0] < WIN_N:
            return None
        f = extract_features(wav)
        cls, grade, conf, exp = classify(f, event_ms)
        # Reportable events get the full evidence window; informational ones are
        # trimmed so the buffer cost tracks operational value.
        if grade == 0 and len(wav) > PRE_N + POST_N:
            wav = wav[: PRE_N + POST_N]
        return ImpactEvent(
            t_host_ms=t0, t_close_ms=now_ms, wav=wav, wav_t0_ms=t0,
            peak_g=np.array([f["peaks"][z] for z in ZONES], dtype=np.float32),
            nzones=f["nzones"],
            onset_ms=np.zeros(NZONES, dtype=np.float32),
            features=f, cls=cls, grade=grade, conf=conf, explanations=exp,
        )


def run_channel(ch, block_ms: int = 100) -> list[ImpactEvent]:
    det = ImpactDetector(ch.dev_id)
    bs = FS * block_ms // 1000
    events: list[ImpactEvent] = []
    for s in range(0, ch.n, bs):
        events.extend(det.process(ch.x[s:s + bs]))
    # Flush any open event at end of stream.
    if det.in_event:
        ev = det._close(det.t_ms + POST_MS)
        if ev:
            events.append(ev)
    return events