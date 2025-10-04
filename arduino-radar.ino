#include <Servo.h>

//Pins (UNO)
const uint8_t TRIG = 6;       // HC-SR04 TRIG
const uint8_t ECHO = 5;       // HC-SR04 ECHO (5V tolerant on UNO)
const uint8_t SERVO_PIN = 8;  // servo signal

//Timing
const unsigned long PULSE_TIMEOUT_US = 20000UL; // 20 ms (~3.4 m max)
const uint16_t SETTLE_AFTER_MOVE_MS  = 30;      // let horn stop wobbling
const uint16_t MIN_PING_PERIOD_MS    = 60;      // HC-SR04 needs >= 60 ms

//Constants
const float SOUND_CM_PER_US = 0.0343f;

Servo servoMotor;

// Single ping. Returns NaN on timeout/out-of-range.
float pingOnce(unsigned long &dur) {
  digitalWrite(TRIG, LOW);  delayMicroseconds(2);
  digitalWrite(TRIG, HIGH); delayMicroseconds(10);
  digitalWrite(TRIG, LOW);

  dur = pulseIn(ECHO, HIGH, PULSE_TIMEOUT_US);
  if (dur == 0) return NAN;

  float d = (dur * SOUND_CM_PER_US) / 2.0f;
  if (d > 400.0f) return NAN;
  return d;
}

// Median of up to 3 values, ignoring NaNs; NaN if all invalid.
float median3_ignoreNaN(float a, float b, float c) {
  float v[3]; uint8_t n = 0;
  if (!isnan(a)) v[n++] = a;
  if (!isnan(b)) v[n++] = b;
  if (!isnan(c)) v[n++] = c;
  if (n == 0) return NAN;
  // insertion sort for up to 3
  for (uint8_t i=1;i<n;i++){
    float key=v[i]; int j=i-1;
    while (j>=0 && v[j]>key){ v[j+1]=v[j]; j--; }
    v[j+1]=key;
  }
  // median
  return v[n/2];
}

void setup() {
  pinMode(TRIG, OUTPUT);
  pinMode(ECHO, INPUT);
  digitalWrite(TRIG, LOW);

  servoMotor.attach(SERVO_PIN);
  servoMotor.write(0);

  Serial.begin(115200);   //Python/Serial Monitor to 115200
  delay(1000);
  Serial.println("START");
}

void measureAndPrintAtAngle(int angle) {
  servoMotor.write(angle);
  delay(SETTLE_AFTER_MOVE_MS);   // 1) settle

  // 2) ping 3× quickly
  unsigned long d1u, d2u, d3u;
  float d1 = pingOnce(d1u); delay(10);
  float d2 = pingOnce(d2u); delay(10);
  float d3 = pingOnce(d3u);

  float dmed = median3_ignoreNaN(d1, d2, d3);

  // 3) print once per angle (CSV expected by  Python)
  Serial.print(angle);
  Serial.print(',');
  if (isnan(dmed)) Serial.println("NA");
  else             Serial.println(dmed, 2);

  // 4) respect sensor cadence
  delay(MIN_PING_PERIOD_MS);
}

void loop() {
  for (int a = 0; a <= 180; ++a)  measureAndPrintAtAngle(a);
  for (int a = 180; a >= 0; --a)  measureAndPrintAtAngle(a);
}
