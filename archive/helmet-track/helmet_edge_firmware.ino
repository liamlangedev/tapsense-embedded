// ESP32 single-sensor current monitor
// GPIO34 is ADC input only. Serial: 115200 baud, one JSON reading per 100 ms.
// Set SHUNT_OHMS to the actual resistor value before trusting current_a.

#include <Arduino.h>

const uint8_t SENSOR_PIN = 34;
const float SHUNT_OHMS = 1.0f;  // CHANGE to the resistor's measured value
const uint32_t SAMPLE_PERIOD_MS = 100;
uint32_t next_sample_ms = 0;

void setup() {
  Serial.begin(115200);
  analogReadResolution(12);
  analogSetPinAttenuation(SENSOR_PIN, ADC_11db);
  next_sample_ms = millis();
}

void loop() {
  const uint32_t now = millis();
  if ((int32_t)(now - next_sample_ms) < 0) return;
  next_sample_ms += SAMPLE_PERIOD_MS;

  const uint16_t raw_adc = analogRead(SENSOR_PIN);
  const uint32_t millivolts = analogReadMilliVolts(SENSOR_PIN);
  const float voltage_v = millivolts / 1000.0f;
  const float current_a = voltage_v / SHUNT_OHMS;

  Serial.printf(
    "{\"type\":\"sample\",\"timestamp_ms\":%lu,\"gpio\":34,"
    "\"raw_adc\":%u,\"voltage_v\":%.4f,\"shunt_ohms\":%.4f,"
    "\"current_a\":%.4f}\n",
    (unsigned long)now, raw_adc, voltage_v, SHUNT_OHMS, current_a
  );
}
