# Architecture

Sensor-to-dashboard chain as it was built during the hackathon.

```
┌──────────────────┐   5V analog      ┌──────────────────┐   CSV 115200   ┌──────────────────┐
│  FSR pad (A0)    │ ───────────────▶ │  Arduino Nano    │ ─────────────▶ │  ESP8266         │
│  FSR pad (A1)    │                  │  3-zone readout  │  1k/2k divider │  FSR-Hub         │
│  FSR pad (A2)    │                  │  50 Hz, labelled │  on D7         │  AP + WebServer  │
└──────────────────┘                  └──────────────────┘                └────────┬─────────┘
                                                                                   │
                                                         Wi-Fi (own AP)            │
                                              ssid FSR-Hub / fsr-sensor             │
                                                                                   ▼
                                                                        ┌──────────────────┐
                                                                        │  Phone / Laptop  │
                                                                        │  http://192.168  │
                                                                        │       .4.1/      │
                                                                        └──────────────────┘

                                                        later:  Raspberry Pi joins FSR-Hub
                                                                and consumes GET /data
```

## Design decisions

**Why the Nano does the analog read, not the ESP8266.**
The FSR pads need three analog channels sampled continuously at 50 Hz. The ESP8266
has a single usable ADC with a known nonlinearity, so the Nano owns the sensor
side and stays a dumb, well-tested CSV source. It can still be watched in the
Arduino Serial Plotter without any of the Wi-Fi code running.

**Why a software UART instead of the hardware RX pin.**
GPIO3/RX on an ESP8266 dev board is wired to the USB programming interface. Using
it for the Nano means unplugging the wire on every upload and fighting boot noise
at 74880 baud. Moving the Nano input to D7 (GPIO13) with `SoftwareSerial` keeps
flashing painless. Cost: no hardware UART buffer, which is fine at 115200 with
96-byte lines and a discard-on-overflow policy.

**Why a 5 V → 3.3 V divider.**
The Nano drives 5 V logic. Feeding that straight into a 3.3 V-only ESP8266 RX pin
is the classic way to end an evening early. 1 kΩ in series, 2 kΩ to ground.

**Why the ESP8266 is the AP, not a client.**
No venue Wi-Fi, no router, no Pi at the time. The hub brings its own network, so a
phone can connect and see the value with zero infrastructure. The Pi later joins
the same AP and reads the same stable `GET /data` endpoint — no change to the
firmware.

**Why the payload is tiny.**
A soldier who cannot reach a radio needs a gesture that still works. Two, three or
four taps are distinguishable from a single bump and can be classified on-device.
Only the classification needs to leave the device, not the raw stream.

## Bandwidth / latency budget

| Hop | Format | Rate |
|---|---|---|
| FSR → Nano | analog, 10-bit | 3 ch × 50 Hz |
| Nano → ESP | labelled ASCII CSV | ~40 B per line, 50 lines/s |
| ESP → client | JSON over HTTP | polled every 100 ms |
| ESP → OLED | local render | 1 Hz |

The ESP-to-client hop is deliberately low-bandwidth and pull-based. It works over a
degraded link and it is trivial to replace with BLE or a store-and-forward queue.

## Known gaps

See [PROTOCOL.md](PROTOCOL.md) for the exact contract and the unfinished part.
Short version: the tap → event mapping exists on the OLED but was never promoted
into the JSON API. The `/data` endpoint currently exposes only the raw Zone-1 value
and a threshold-derived `pressed` flag.
