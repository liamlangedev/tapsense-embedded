#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# flash.sh  —  Build and flash sensor_current_monitor.ino
# Usage:
#   ./flash.sh                  auto-detect port
#   ./flash.sh /dev/ttyUSB1     override port
# ──────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SKETCH="sensor_current_monitor.ino"
FQBN="esp32:esp32:esp32minikit"
BAUD=115200

# ── Find port ─────────────────────────────────────────────────────────────────
if [[ $# -ge 1 ]]; then
  PORT="$1"
else
  PORT=$(ls /dev/ttyUSB* /dev/ttyACM* 2>/dev/null | head -1)
  if [[ -z "$PORT" ]]; then
    echo "ERROR: no serial port found. Plug in the ESP32 or pass port as arg."
    exit 1
  fi
  echo "Using port: $PORT"
fi

# ── Check arduino-cli ─────────────────────────────────────────────────────────
if ! command -v arduino-cli &>/dev/null; then
  echo "arduino-cli not found. Install:"
  echo "  curl -fsSL https://raw.githubusercontent.com/arduino/arduino-cli/master/install.sh | sh"
  exit 1
fi

# ── Install board core if missing ─────────────────────────────────────────────
if ! arduino-cli board listall | grep -q "esp32:esp32"; then
  echo "Installing ESP32 board core..."
  arduino-cli config add board_manager.additional_urls \
    https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json
  arduino-cli core update-index
  arduino-cli core install esp32:esp32
fi

# ── Install libraries if missing ──────────────────────────────────────────────
for LIB in "ESP Async WebServer" "AsyncTCP"; do
  if ! arduino-cli lib list | grep -q "$LIB"; then
    echo "Installing library: $LIB"
    arduino-cli lib install "$LIB"
  fi
done

# ── Compile & upload ──────────────────────────────────────────────────────────
echo ""
echo "Compiling $SKETCH..."
arduino-cli compile --fqbn "$FQBN" "$SKETCH"

echo ""
echo "Uploading to $PORT..."
arduino-cli upload --fqbn "$FQBN" --port "$PORT" "$SKETCH"

echo ""
echo "Done! Opening serial monitor..."
echo "Press Ctrl+C to stop. The IP address will appear on the first boot."
echo ""
arduino-cli monitor --port "$PORT" --config "baudrate=$BAUD"
