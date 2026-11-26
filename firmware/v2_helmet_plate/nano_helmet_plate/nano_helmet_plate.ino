/*
 * TapSense v2 — 4-Zone Helmet + Plate Carrier Sensor Node (Arduino Nano)
 *
 * Samples five CurveSYS / FSR voltage dividers at 100 Hz (10 ms cadence):
 *   A0 : Helmet Front  (0 deg  / N)
 *   A1 : Helmet Right  (90 deg / E)
 *   A2 : Helmet Back   (180 deg / S)
 *   A3 : Helmet Left   (270 deg / W)
 *   A4 : Plate Carrier Gesture Pad (chest/shoulder tap trigger)
 *
 * Wiring per channel: 5V -> FSR -> Analog Pin -> 10 kOhm -> GND.
 * Output: labelled ASCII CSV at 115200 baud:
 *   H_N:<int>,H_E:<int>,H_S:<int>,H_W:<int>,P_TAP:<int>\n
 *
 * 100 Hz gives 10 ms resolution so sharp helmet impacts can be separated
 * from slow static preload (helmet strap tension or leaning).
 */

const uint8_t PIN_HELMET_N = A0;
const uint8_t PIN_HELMET_E = A1;
const uint8_t PIN_HELMET_S = A2;
const uint8_t PIN_HELMET_W = A3;
const uint8_t PIN_PLATE_TAP = A4;

const unsigned long SAMPLE_INTERVAL_MS = 10;  // 100 Hz
unsigned long lastSampleAt = 0;

void setup() {
  Serial.begin(115200);
}

void loop() {
  const unsigned long now = millis();
  if (now - lastSampleAt < SAMPLE_INTERVAL_MS) {
    return;
  }
  lastSampleAt = now;

  const int hN = analogRead(PIN_HELMET_N);
  const int hE = analogRead(PIN_HELMET_E);
  const int hS = analogRead(PIN_HELMET_S);
  const int hW = analogRead(PIN_HELMET_W);
  const int pTap = analogRead(PIN_PLATE_TAP);

  Serial.print(F("H_N:"));
  Serial.print(hN);
  Serial.print(F(",H_E:"));
  Serial.print(hE);
  Serial.print(F(",H_S:"));
  Serial.print(hS);
  Serial.print(F(",H_W:"));
  Serial.print(hW);
  Serial.print(F(",P_TAP:"));
  Serial.println(pTap);
}
