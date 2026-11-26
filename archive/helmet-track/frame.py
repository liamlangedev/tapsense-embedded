"""Compact, signed alert frame.

Wire budget target: one LoRa SF9/125 kHz packet (<= 222 B). The frame carries
enough for a commander to act (what, where, how hard, how sure, when) plus a
commitment to the raw waveform that stays on the device until it is challenged.

Layout (little endian, canonical bytes = payload only):

    off  len  field
      0    1  ver
      1    4  dev_id (ascii)
      5    3  boot_id
      8    4  seq                monotonic per device
     12    4  t_ms               device monotonic clock, ms since boot
     16    6  t_wall_ms          40..87 bit epoch ms (48 bit)
     22    1  grade              0..4
     23    1  cls                0..4
     24    1  conf               0..100
     25    1  zones              bitmask
     26    1  nzones
     27    2  peak_dg            deci-g, capped 6553.5 g
     29    2  impulse_dg         g^2*s * 1000, capped
     31    2  dur_ms
     33    2  rise_us
     35    2  centroid_hz
     37    2  ev_len_ms
     39    2  lat_ms             device internal detect->sign latency
     41   32  ev_digest          sha256 over the evidence bundle
     73    8  chain              first 8 bytes of sha256(previous frame)
     81   64  sig                Ed25519 over payload[0:81]
    ---
     145  total
"""

from __future__ import annotations

import hashlib
import struct
import time

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from .params import GRADES, CLASSES, SIG_BYTES, VER

_HDR = struct.Struct("<B4s3sII6sBBBBbHHHHHHH32s8s")
PAYLOAD_BYTES = _HDR.size + SIG_BYTES
assert _HDR.size == 81, _HDR.size

_U16_CAP = 0xFFFF


def _clamp_u16(v: float) -> int:
    return max(0, min(_U16_CAP, int(round(v))))


class AlertFrame:
    """A single signed impact alert."""

    __slots__ = (
        "ver", "dev_id", "boot_id", "seq", "t_ms", "t_wall_ms", "grade", "cls",
        "conf", "zones", "nzones", "peak_dg", "impulse_dg", "dur_ms", "rise_us",
        "centroid_hz", "ev_len_ms", "lat_ms", "ev_digest", "chain", "sig",
    )

    def __init__(self, *, dev_id: str, boot_id: bytes, seq: int, t_ms: int,
                 t_wall_ms: int, grade: int, cls: int, conf: int, zones: int,
                 nzones: int, peak_dg: int, impulse_dg: int, dur_ms: int,
                 rise_us: int, centroid_hz: int, ev_len_ms: int, lat_ms: int,
                 ev_digest: bytes, chain: bytes, ver: int = VER, sig: bytes = b""):
        self.ver = ver
        self.dev_id = dev_id
        self.boot_id = boot_id
        self.seq = seq
        self.t_ms = t_ms
        self.t_wall_ms = t_wall_ms
        self.grade = grade
        self.cls = cls
        self.conf = conf
        self.zones = zones
        self.nzones = nzones
        self.peak_dg = peak_dg
        self.impulse_dg = impulse_dg
        self.dur_ms = dur_ms
        self.rise_us = rise_us
        self.centroid_hz = centroid_hz
        self.ev_len_ms = ev_len_ms
        self.lat_ms = lat_ms
        self.ev_digest = ev_digest
        self.chain = chain
        self.sig = sig

    # ---- serialisation -------------------------------------------------
    def payload(self) -> bytes:
        return _HDR.pack(
            self.ver,
            self.dev_id.encode()[:4].ljust(4, b"\0"),
            self.boot_id[:3].ljust(3, b"\0"),
            self.seq & 0xFFFFFFFF,
            self.t_ms & 0xFFFFFFFF,
            self.t_wall_ms.to_bytes(6, "little"),
            self.grade,
            self.cls,
            self.conf,
            self.zones,
            self.nzones,
            _clamp_u16(self.peak_dg),
            _clamp_u16(self.impulse_dg),
            _clamp_u16(self.dur_ms),
            _clamp_u16(self.rise_us),
            _clamp_u16(self.centroid_hz),
            _clamp_u16(self.ev_len_ms),
            _clamp_u16(self.lat_ms),
            self.ev_digest.ljust(32, b"\0")[:32],
            self.chain.ljust(8, b"\0")[:8],
        )

    def to_bytes(self) -> bytes:
        return self.payload() + self.sig

    @classmethod
    def from_bytes(cls, blob: bytes) -> "AlertFrame":
        if len(blob) != PAYLOAD_BYTES:
            raise ValueError(f"frame must be {PAYLOAD_BYTES} B, got {len(blob)}")
        payload, sig = blob[:81], blob[81:]
        (ver, dev, boot, seq, t_ms, t_wall6, grade, cls, conf, zones, nzones,
         peak, imp, dur, rise, cen, evlen, lat, digest, chain) = _HDR.unpack(payload)
        return cls(
            dev_id=dev.rstrip(b"\0").decode(errors="replace"), boot_id=boot,
            seq=seq, t_ms=t_ms, t_wall_ms=int.from_bytes(t_wall6, "little"),
            grade=grade, cls=cls, conf=conf, zones=zones, nzones=nzones,
            peak_dg=peak, impulse_dg=imp, dur_ms=dur, rise_us=rise,
            centroid_hz=cen, ev_len_ms=evlen, lat_ms=lat, ev_digest=digest,
            chain=chain, ver=ver, sig=sig,
        )

    def frame_id(self) -> bytes:
        """Identity of the frame = sha256(payload || sig). Used for chaining."""
        return hashlib.sha256(self.to_bytes()).digest()

    def sign(self, sk: Ed25519PrivateKey) -> "AlertFrame":
        self.sig = sk.sign(self.payload())
        return self

    def verify(self, pk: Ed25519PublicKey) -> bool:
        try:
            pk.verify(self.sig, self.payload())
            return True
        except InvalidSignature:
            return False

    # ---- helpers -------------------------------------------------------
    @property
    def class_name(self) -> str:
        return CLASSES[self.cls] if 0 <= self.cls < len(CLASSES) else "unknown"

    @property
    def grade_name(self) -> str:
        return GRADES[self.grade] if 0 <= self.grade < len(GRADES) else "unknown"

    def zone_names(self) -> list[str]:
        from .params import ZONES
        return [z for i, z in enumerate(ZONES) if self.zones >> i & 1]

    def to_dict(self) -> dict:
        return {
            "dev_id": self.dev_id,
            "boot_id": self.boot_id.hex(),
            "seq": self.seq,
            "t_ms": self.t_ms,
            "t_wall_ms": self.t_wall_ms,
            "t_iso": time.strftime("%H:%M:%S", time.gmtime(self.t_wall_ms / 1000))
                     + f".{self.t_wall_ms % 1000:03d}Z",
            "grade": self.grade,
            "grade_name": self.grade_name,
            "cls": self.cls,
            "class_name": self.class_name,
            "conf": self.conf,
            "zones": self.zone_names(),
            "zone_mask": self.zones,
            "nzones": self.nzones,
            "peak_g": round(self.peak_dg / 10, 1),
            "impulse": round(self.impulse_dg / 1000, 3),
            "dur_ms": self.dur_ms,
            "rise_us": self.rise_us,
            "centroid_hz": self.centroid_hz,
            "ev_len_ms": self.ev_len_ms,
            "lat_ms": self.lat_ms,
            "ev_digest": self.ev_digest.hex(),
            "chain": self.chain.hex(),
            "frame_id": self.frame_id().hex(),
            "bytes": PAYLOAD_BYTES,
            "sig": self.sig.hex(),
        }


def digest_chain(prev_id: bytes) -> bytes:
    """Chain field for the next frame."""
    return prev_id[:8] if prev_id else b"\0" * 8