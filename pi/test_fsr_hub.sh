#!/usr/bin/env bash
set -euo pipefail

ssid='FSR-Hub'
password='fsr-sensor'
url='http://192.168.4.1/data'

nmcli device wifi connect "$ssid" password "$password"

for attempt in 1 2 3 4 5; do
  if response=$(curl --connect-timeout 3 --max-time 5 -fsS "$url"); then
    printf 'FSR-Hub /data: %s\n' "$response"
    exit 0
  fi
  printf 'Waiting for FSR-Hub API (%s/5)\n' "$attempt" >&2
  sleep 1
done
printf 'Could not read %s; confirm the ESP8266 hub is powered and its sketch is running.\n' "$url" >&2
exit 1
