// Arduino Nano: 3-zone FSR Serial Plotter
// Connect each FSR from 5V to A0/A1/A2; connect a 10kΩ resistor
// from each analog pin to GND (one voltage divider per sensor).

const int pinPad1 = A0;
const int pinPad2 = A1;
const int pinPad3 = A2;

void setup() {
  Serial.begin(115200);
}

void loop() {
  int p1 = analogRead(pinPad1);
  int p2 = analogRead(pinPad2);
  int p3 = analogRead(pinPad3);

  Serial.print("Pad1_A0:");
  Serial.print(p1);
  Serial.print(",Pad2_A1:");
  Serial.print(p2);
  Serial.print(",Pad3_A2:");
  Serial.println(p3);

  delay(20); // 50 Hz
}
