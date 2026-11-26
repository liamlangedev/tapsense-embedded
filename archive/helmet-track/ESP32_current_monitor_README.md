# ESP32 Sensor Current Monitor

## Hardware Wiring

```
                    ┌─────────────┐
    3.3V ───────┬───┤   Sensor    ├───┬────── GND
                │   └─────────────┘   │
                │                     │
                ├─────────────────────┤
                │                     │
               ┌┴┐                   ┌┴┐
               │ │ Sensor            │ │ 10kΩ Shunt
               │ │ (unknown R)       │ │ 
               └┬┘                   └┬┘
                │                     │
                └──────┬─────────────┘
                       │
                    GPIO34 (IO34)
                    ADC1_CH6
```

### Connections
- **IO34** → Junction between sensor and 10kΩ shunt resistor
- **GND** → Ground rail
- **3.3V** → Supply rail (or use external power)

⚠️ **IO34 is input-only** — ADC range 0–3.3V with 11dB attenuation

---

## Software Setup

### Before Flashing
1. **Edit WiFi credentials** in `sensor_current_monitor.ino`:
   ```cpp
   const char* WIFI_SSID = "YOUR_WIFI_SSID";
   const char* WIFI_PASS = "YOUR_WIFI_PASSWORD";
   ```

### Install Dependencies
If `arduino-cli` is not installed:
```bash
curl -fsSL https://raw.githubusercontent.com/arduino/arduino-cli/master/install.sh | sh
```

Libraries (auto-installed by flash script):
- ESP Async WebServer
- AsyncTCP

### Flash Firmware
```bash
./flash.sh                # auto-detect USB port
./flash.sh /dev/ttyUSB1   # specify port manually
```

The script will:
1. Install ESP32 board core (if missing)
2. Install required libraries
3. Compile the sketch
4. Upload to the ESP32
5. Open serial monitor to show the IP address

---

## Usage

1. Power on the ESP32 after flashing
2. Wait for WiFi connection (serial monitor shows IP)
3. Open browser: `http://<ESP_IP>`
4. Dashboard shows live voltage, current, and resistance
5. Real-time graphs display the last 200 samples

### Dashboard Features
- **Voltage trace** (cyan) — voltage across 10kΩ shunt
- **Current trace** (emerald) — calculated from V = I×R
- **Resistance value** — derived from V/I ratio
- **10 Hz sampling** with 16× oversampling for noise reduction

---

## Measurement Notes

Current formula:
```
I = V_measured / R_shunt
I = V_measured / 10000 Ω
```

If sensor is in series with shunt, measured voltage is across the shunt only.

To calculate **sensor resistance** accurately, you need:
1. Supply voltage (V_supply)
2. Voltage across shunt (V_shunt, measured at IO34)
3. Then: `R_sensor = (V_supply - V_shunt) / I - R_shunt`

Current firmware shows approximate resistance from `V/I` ratio — update formula once you measure supply voltage.

---

## Serial Monitor Output
```
V=0.125V  I=0.013mA  R=9821.4Ω
V=0.126V  I=0.013mA  R=9846.2Ω
```

Baud rate: **115200**
