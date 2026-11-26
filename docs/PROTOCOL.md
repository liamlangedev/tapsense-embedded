# Wire formats and HTTP API

Two hops carry data in this build: Nano → ESP over UART, and ESP → client over Wi-Fi.

## 1. Nano → ESP8266 (UART, 115200 8N1)

The Nano emits one labelled CSV line per sample, roughly every 20 ms (50 Hz):

```
Pad1_A0:512,Pad2_A1:0,Pad3_A2:7
```

- Line terminator: `\n`.
- Every field is `PadN_Ax:<integer>`, ADC range `0–1023` (10-bit ATmega).
- The labels exist so the ESP can pick fields by name and stay correct if a zone is
  disabled or the order changes. The ESP currently only consumes `Pad1_A0`.

The ESP reads this on a **software UART** (`SoftwareSerial nanoSerial(D7, -1)`)
because its hardware UART is the USB programming port. No debug output is printed to
the Nano from the ESP direction — the wire is one-way.

### Parser rules (as implemented)

- Line buffer is 96 bytes. An overlong line is dropped in full rather than truncated,
  and the parser resyncs on the next `\n`. A partial line never updates state.
- A field only counts if the digits are contiguous and all numeric; overflow past
  `LONG_MAX` is rejected. A malformed field does not overwrite the last good value.
- `Pad1_A0:` matches on exactly 7 characters before the colon.

## 2. ESP8266 → client (HTTP)

The ESP runs as its own access point:

| | |
|---|---|
| SSID | `FSR-Hub` |
| Password | `fsr-sensor` |
| ESP address | `192.168.4.1` |

### `GET /`

Returns the embedded single-page UI: a live status line, the current A0 value, an
ON/OFF state label, and a scrolling on/off graph (last 150 samples). It polls
`/data` every 100 ms and shows `Waiting for sensor data (...)` on failure, then
resumes automatically when the ESP comes back.

### `GET /data`

- **`503`** before the first valid sample: `{"error":"waiting_for_nano"}`
- **`200`** afterwards:

```json
{"a0": 512, "pressed": true}
```

`pressed` is `true` when `a0 >= tapPressThreshold` (150). The last good value is kept
even if no newer sample arrives, so a client poll never sees a blank.

This endpoint is additive-only in practice: the Pi was planned to depend on it, so new
fields are added without renaming existing ones.

## 3. Intended event packet (the gap)

This is the contract we designed and did not finish wiring up. The tap classifier
already runs on the ESP — it counts momentary pressure transitions within
`tapGapMs = 400` ms and maps:

| Taps | Meaning | Intended `event_type` |
|---|---|---|
| 2 | Distress | `critical_situation` |
| 3 | Medical | `medical_supply_drone_request` |
| 4 | Resupply | `game_backup_resupply_request` |
| other | Ignored | `none` |

The intended payload extends the current one rather than replacing it:

```json
{
  "a0": 512,
  "pressed": true,
  "tap_count": 3,
  "event_id": 17,
  "event_type": "medical_supply_drone_request"
}
```

`event_id` would increment once per completed gesture so a consumer can de-duplicate:
the value is stable between gestures, so a Pi that polls faster than the human taps
sees the same event id until a new gesture completes.

Restoring it means adding the fields to the `snprintf` in `handleData()` — the
state variables (`eventTapCount`, `eventId`) already exist and are already updated.

## 4. Pi side

The Pi joins `FSR-Hub` and either polls `/data` directly (as `pi/test_fsr_hub.sh`
does) or runs `pi/sensor_bridge.py`, which reads a local serial port and fans out to
WebSocket clients on `127.0.0.1:8889`. `pi/live_graph.html` and `pi/dashboard.html`
connect to that socket.

`pi/config-pi-wifi.sh` pre-bakes Wi-Fi credentials into a Raspberry Pi OS image by
mounting the boot partition at byte offset `8388608` and rewriting `network-config`,
so a fresh Pi joins the hub on first boot with no monitor or keyboard.

## 5. Target architecture v2 (`firmware/v2_helmet_plate/`)

The v2 firmware extends the protocol to a 4-zone directional helmet array (`A0`–`A3`)
plus a dedicated plate-carrier tap pad (`A4`).

### Nano → ESP8266 CSV (100 Hz, 115200 8N1)

```
H_N:18,H_E:420,H_S:12,H_W:15,P_TAP:0
```

- `H_N` (`A0`, 0° Front), `H_E` (`A1`, 90° Right), `H_S` (`A2`, 180° Back), `H_W` (`A3`, 270° Left)
- `P_TAP` (`A4`, chest/shoulder gesture pad)

### `GET /data` (v2)

Returns the current 5-channel snapshot, latest computed helmet impact vector, and
latest plate gesture state:

```json
{
  "helmet": {
    "n": 18, "e": 420, "s": 12, "w": 15,
    "direction_deg": 89, "cardinal": "E",
    "peak": 405, "severity": "MEDIUM", "confidence": 88
  },
  "plate": { "a4": 0, "pressed": false },
  "gesture": { "tap_count": 3, "event_type": "medical_supply_drone_request" }
}
```

### `GET /events?since=<id>` (v2 store-and-forward)

Returns all buffered events from the 16-slot ring buffer with `id > since`:

```json
{
  "events": [
    {
      "id": 1,
      "ts_ms": 1420,
      "kind": "HELMET_IMPACT",
      "event_type": "helmet_impact_detected",
      "tap_count": 0,
      "direction_deg": 48,
      "cardinal": "NE",
      "peak_force": 512,
      "severity": "MEDIUM",
      "confidence": 87,
      "impact_age_ms": 0
    },
    {
      "id": 2,
      "ts_ms": 3890,
      "kind": "GESTURE",
      "event_type": "medical_supply_drone_request",
      "tap_count": 3,
      "direction_deg": 48,
      "cardinal": "NE",
      "peak_force": 512,
      "severity": "MEDIUM",
      "confidence": 87,
      "impact_age_ms": 2470
    }
  ]
}
```

`pi/tapsense_pi_client.py` polls this endpoint, persists each event to JSONL, and
forwards `GESTURE` missions (including the attached `helmet_impact` vector) to the
autonomous drone / C2 webhook.

