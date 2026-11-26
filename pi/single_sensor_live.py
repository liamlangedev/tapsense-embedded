#!/usr/bin/env python3
"""Single sensor live streamer — reads GPIO34 analog, outputs events when threshold hit"""
import json
import time
import random
import sys

# Simulate single ADC reading (0-4095 range like ESP32 ADC)
def read_adc():
    """Mock ADC read — replace with real serial.readline() from ESP32"""
    # Simulate noise floor + occasional spikes
    base = random.randint(50, 150)
    if random.random() < 0.1:  # 10% chance of hit
        return base + random.randint(500, 3800)
    return base

seq = 0
last_hit_time = 0

def classify_event(force, time_since_last):
    """Classify based on single sensor force"""
    global seq
    seq += 1
    
    is_double = time_since_last < 0.3
    
    if is_double:
        event_type = "DOUBLE_TAP"
        severity = "CRITICAL"
    elif force > 2500:
        event_type = "KINETIC_HEAVY"
        severity = "CRITICAL"
    elif force > 1500:
        event_type = "SINGLE_TAP"
        severity = "MEDIUM"
    elif force > 500:
        event_type = "SINGLE_TAP"
        severity = "LOW"
    else:
        event_type = "GLANCING_BLOW"
        severity = "LOW"
    
    confidence = min(1.0, force / 4000.0)
    
    return {
        "soldier_id": "ALPHA",
        "seq": seq,
        "timestamp_ms": int(time.time() * 1000),
        "event_type": event_type,
        "severity": severity,
        "primary_zone": "SENSOR",
        "direction_deg": 0,
        "peak_force": force,
        "confidence": round(confidence, 2),
        "raw_zones": {"sensor": force},
        "sig": f"{force:08x}{seq:08x}"
    }

print("🎯 Single Sensor Live — GPIO34 mock stream", file=sys.stderr)
print("Hit Ctrl+C to stop", file=sys.stderr)

try:
    while True:
        force = read_adc()
        
        if force > 500:  # Threshold
            now = time.time()
            time_since_last = now - last_hit_time
            last_hit_time = now
            
            event = classify_event(force, time_since_last)
            print(json.dumps(event), flush=True)
            print(f"  💥 Hit detected: {force} → {event['event_type']}", file=sys.stderr)
            time.sleep(0.05)  # Debounce
        
        time.sleep(0.01)  # 100Hz sample rate
        
except KeyboardInterrupt:
    print("\n✅ Stopped", file=sys.stderr)
