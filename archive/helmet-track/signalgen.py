"""Synthetic multi-zone helmet impact signals.

Deterministic (seeded) so a demo run is reproducible on any laptop. The point
is not photo-realism but the *decision-relevant* structure: a real fragment hit
has a fast rise, high spectral centroid and a short ring; a doorframe bump is
slow, low-frequency and single-zone; a blast loads almost every zone at once
with a long low-frequency ramp; a loose connector hums at 50 Hz forever.
"""

from __future__ import annotations

import numpy as np

from .params import FS, NZONES, ZONE_IDX, ZONES


class Channel:
    """One device's 8-zone accelerometer stream plus its ground truth."""

    def __init__(self, dev_id: str, duration_s: float, seed: int):
        self.dev_id = dev_id
        self.fs = FS
        self.n = int(duration_s * FS)
        self.rng = np.random.default_rng(seed)
        self.x = np.zeros((self.n, NZONES), dtype=np.float32)
        self.truth: list[dict] = []
        self._baseline()

    # -- backgrounds -----------------------------------------------------
    def _baseline(self) -> None:
        n = self.n
        t = np.arange(n) / self.fs
        rng = self.rng
        # Posture sway / walking: 1-4 Hz, 0.4-1.6 g, strongly coherent.
        sway = np.zeros(n, dtype=np.float32)
        for f, a in ((1.1 + rng.uniform(0, 0.4), 0.9), (2.4 + rng.uniform(0, 0.6), 0.45),
                     (3.7 + rng.uniform(0, 0.8), 0.22)):
            sway += (a * np.sin(2 * np.pi * f * t + rng.uniform(0, 6.28))).astype(np.float32)
        sway *= (0.6 + 0.4 * np.abs(np.sin(2 * np.pi * 0.13 * t))).astype(np.float32)
        # Breathing: mild, mostly on the crown.
        sway += (0.18 * np.sin(2 * np.pi * 0.28 * t)).astype(np.float32)
        for i, z in enumerate(ZONES):
            gain = 1.0 if z != "T" else 0.55
            self.x[:, i] += sway * gain
        # Sensor noise: white, 0.12 g rms, slightly different per zone.
        self.x += rng.normal(0, 0.12, size=(n, NZONES)).astype(np.float32)

    def _add(self, t0_s: float, wave: np.ndarray, zones: dict[str, float]) -> None:
        s = int(round(t0_s * self.fs))
        if s < 0 or s >= self.n:
            return
        e = min(self.n, s + len(wave))
        seg = wave[: e - s]
        for z, g in zones.items():
            self.x[s:e, ZONE_IDX[z]] += (seg * g).astype(np.float32)

    # -- event primitives ------------------------------------------------
    def _shock(self, f_hz: float, tau_s: float, attack_s: float, dur_s: float,
               jitter: float = 0.05) -> np.ndarray:
        n = int(dur_s * self.fs)
        t = np.arange(n) / self.fs
        attack = np.clip(t / max(attack_s, 1e-6), 0.0, 1.0)
        ring = np.exp(-(t - attack_s).clip(0) / tau_s) * (t >= attack_s * 0.35)
        w = attack * ring * np.sin(2 * np.pi * f_hz * t)
        if jitter:
            w = w + 0.18 * self.rng.normal(0, 1, n) * np.exp(-t / (tau_s * 0.7))
        return w.astype(np.float32)

    # -- event types -----------------------------------------------------
    def blast(self, t0: float, peaki_g: float, *, origin_zone: str = "F",
              slow: float = 1.0) -> dict:
        """Overpressure: quasi-simultaneous load on nearly all zones."""
        dur = 0.30 * slow
        wave = self._shock(85.0, 0.075 * slow, 0.009 * slow, dur, jitter=0.3)
        # Broadband precursor of the detonation front.
        n = int(dur * self.fs)
        prec = self.rng.normal(0, 1, n) * np.exp(-np.arange(n) / (0.02 * self.fs))
        wave = wave + 0.25 * prec.astype(np.float32)
        wave = wave / (np.abs(wave).max() + 1e-9) * peaki_g
        # Falloff with distance from the exposed side; crown is shielded.
        rel = {"F": 1.0, "FR": .95, "FL": .95, "R": .8, "L": .8,
               "BR": .6, "BL": .6, "T": .45}
        zones = {z: rel[z] * self.rng.uniform(0.85, 1.05) for z in ZONES}
        self._add(t0, wave, zones)
        return dict(kind="blast", t=t0, peak=sorted(zones.values())[-1] * peaki_g)

    def fragment(self, t0: float, peaki_g: float, zone: str, spread: float = 0.25) -> dict:
        """Small high-velocity fragment: sharp, high-frequency, localised."""
        wave = self._shock(self.rng.uniform(1400, 2600), 0.0016, 0.00025, 0.030)
        # Rigid-body ringing of the shell right after the strike.
        wave = wave + 0.35 * self._shock(520.0, 0.004, 0.0006, 0.030)
        wave = wave / (np.abs(wave).max() + 1e-9) * peaki_g
        zones = {zone: 1.0}
        for z in ZONES:
            if z != zone and z in _adj(zone):
                zones[z] = spread * self.rng.uniform(0.3, 1.0)
        self._add(t0, wave, zones)
        return dict(kind="fragment_hit", t=t0, peak=peaki_g, zone=zone)

    def blunt(self, t0: float, peaki_g: float, zone: str) -> dict:
        """Doorframe, weapon furniture, vehicle contact: slower, low frequency."""
        wave = self._shock(self.rng.uniform(180, 420), 0.006, 0.0010, 0.060)
        wave = wave / (np.abs(wave).max() + 1e-9) * peaki_g
        zones = {zone: 1.0, }
        for z in ZONES:
            if z != zone and z in _adj(zone):
                zones[z] = 0.2 * self.rng.uniform(0.2, 1.0)
        self._add(t0, wave, zones)
        return dict(kind="blunt_impact", t=t0, peak=peaki_g, zone=zone)

    def handling(self, t0: float, peaki_g: float, zone: str = "T") -> dict:
        """Putting the helmet down, gear rattle. Real signal, not an event."""
        wave = self._shock(self.rng.uniform(90, 180), 0.010, 0.004, 0.090)
        wave = wave / (np.abs(wave).max() + 1e-9) * peaki_g
        self._add(t0, wave, {zone: 1.0, "F": 0.15, "R": 0.15, "L": 0.15})
        return dict(kind="informational", t=t0, peak=peaki_g, zone=zone)

    def fidget(self, t0: float, count: int = 6) -> list[dict]:
        """Hyperactive individual: many small real contacts, no single event."""
        out = []
        for k in range(count):
            t = t0 + k * self.rng.uniform(0.25, 0.8)
            out.append(self.handling(t, self.rng.uniform(4.5, 7.5),
                                     zone=ZONES[int(self.rng.integers(0, 8))]))
        return out

    def vehicle_idle(self, t0: float, dur_s: float, amp_g: float = 1.4) -> dict:
        """Engine vibration: sustained, narrowband, low crest. Must not alarm."""
        n = int(dur_s * self.fs)
        t = np.arange(n) / self.fs
        vib = amp_g * (np.sin(2 * np.pi * 12.0 * t) + 0.5 * np.sin(2 * np.pi * 24.0 * t))
        self._add(t0, vib.astype(np.float32), {"T": 0.9, "F": 0.4, "R": 0.4, "L": 0.4})
        return dict(kind="informational", t=t0, peak=amp_g * 1.5)

    def sensor_fault(self, t0: float, dur_s: float) -> dict:
        """Loose connector: 50 Hz hum with harmonics, occasional contact spikes."""
        n = int(dur_s * self.fs)
        t = np.arange(n) / self.fs
        hum = 1.9 * np.sin(2 * np.pi * 50 * t) + 0.9 * np.sin(2 * np.pi * 150 * t)
        spikes = np.zeros(n, dtype=np.float32)
        for _ in range(int(dur_s / 1.7)):
            i = int(self.rng.integers(0, n))
            spikes[i] = self.rng.uniform(6, 12) * self.rng.choice([-1, 1])
        self._add(t0, (hum + spikes).astype(np.float32), {"BR": 1.0, "R": 0.3})
        return dict(kind="sensor_fault", t=t0, peak=7.0)


def _adj(zone: str) -> set[str]:
    from .params import ADJ
    return ADJ[zone]


# ---------------------------------------------------------------------------
# Mission scenarios
# ---------------------------------------------------------------------------
SCENARIOS: dict[str, dict] = {
    "assault": {
        "title": "Assault on a tree line, 2 fragments + artillery near miss",
        "duration_s": 120,
        "devices": [
            {"dev_id": "S07", "seed": 7, "events": [
                ("handling", 11.5, 6.0, "T"),
                ("blunt", 26.8, 18.0, "FR"),
                ("fragment", 41.40, 65.0, "F"),
                ("fragment", 44.10, 48.0, "FL"),
                ("blast", 52.00, 120.0),
                ("handling", 69.4, 5.2, "T"),
                ("sensor_fault", 88.0, 20.0),
            ]},
            {"dev_id": "S12", "seed": 12, "events": [
                ("blunt", 30.2, 7.5, "BL"),
                ("blunt", 55.10, 22.0, "R"),
                ("blunt", 56.02, 19.0, "BR"),
                ("handling", 100.0, 6.5, "T"),
            ]},
            {"dev_id": "S03", "seed": 3, "events": [
                ("fragment", 41.55, 38.0, "R"),
                ("blast", 52.06, 74.0),
                ("fidget", 95.0),
            ]},
            {"dev_id": "S21", "seed": 21, "events": [
                ("handling", 15.0, 41.0, "T"),
                ("blast", 52.11, 58.0),
                ("vehicle_idle", 101.0, 15.0),
            ]},
        ],
    },
    "quiet": {
        "title": "12 h of a quiet sector: zero reportable events, do not cry wolf",
        "duration_s": 120,
        "devices": [
            {"dev_id": "S07", "seed": 107, "events": [
                ("handling", 8.0, 7.0, "T"),
                ("handling", 33.0, 9.0, "FR"),
                ("fidget", 55.0),
                ("vehicle_idle", 80.0, 25.0, 1.6),
            ]},
            {"dev_id": "S12", "seed": 112, "events": [
                ("handling", 20.0, 11.0, "T"),
                ("sensor_fault", 60.0, 30.0),
                ("fidget", 100.0),
            ]},
        ],
    },
}


def build(dev_id: str, events: list[tuple], duration_s: float, seed: int) -> Channel:
    ch = Channel(dev_id, duration_s, seed)
    for ev in events:
        kind, t0 = ev[0], ev[1]
        if kind == "blast":
            rec = ch.blast(t0, ev[2])
        elif kind == "fragment":
            rec = ch.fragment(t0, ev[2], ev[3])
        elif kind == "blunt":
            rec = ch.blunt(t0, ev[2], ev[3])
        elif kind == "handling":
            rec = ch.handling(t0, ev[2], ev[3])
        elif kind == "fidget":
            recs = ch.fidget(t0)
            ch.truth.extend(recs)
            continue
        elif kind == "vehicle_idle":
            rec = ch.vehicle_idle(t0, ev[2], ev[3] if len(ev) > 3 else 1.4)
        elif kind == "sensor_fault":
            rec = ch.sensor_fault(t0, ev[2])
        else:
            raise ValueError(kind)
        ch.truth.append(rec)
    return ch


def build_scenario(name: str) -> list[Channel]:
    sc = SCENARIOS[name]
    return [build(d["dev_id"], d["events"], sc["duration_s"], d["seed"])
            for d in sc["devices"]]