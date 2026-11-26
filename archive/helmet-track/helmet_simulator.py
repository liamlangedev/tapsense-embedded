#!/usr/bin/env python3
"""Helmet Edge Simulator — 20s test feed with 4 mock events"""
import json
import time
import random
import sys

EVENTS = [
    {
        "soldier_id": "ALPHA", "seq": 101, "timestamp_ms": 482015,
        "event_type": "KINETIC_HEAVY", "severity": "CRITICAL",
        "primary_zone": "FRONT", "direction_deg": 5, "peak_force": 3650,
        "confidence": 0.96,
        "raw_zones": {"front": 3650, "back": 40, "left": 180, "right": 210},
        "sig": "e7b8c491a03f8d22"
    },
    {
        "soldier_id": "ALPHA", "seq": 102, "timestamp_ms": 482250,
        "event_type": "DOUBLE_TAP", "severity": "CRITICAL",
        "primary_zone": "LEFT", "direction_deg": 280, "peak_force": 2980,
        "confidence": 0.91,
        "raw_zones": {"front": 120, "back": 90, "left": 2980, "right": 15},
        "sig": "3a9f11c7bc01d4e2"
    },
    {
        "soldier_id": "BRAVO", "seq": 54, "timestamp_ms": 485120,
        "event_type": "GLANCING_BLOW", "severity": "MEDIUM",
        "primary_zone": "RIGHT", "direction_deg": 85, "peak_force": 890,
        "confidence": 0.48,
        "raw_zones": {"front": 210, "back": 30, "left": 40, "right": 890},
        "sig": "fa0024bb88e1a903"
    },
    {
        "soldier_id": "BRAVO", "seq": 55, "timestamp_ms": 490000,
        "event_type": "SINGLE_TAP", "severity": "LOW",
        "primary_zone": "BACK", "direction_deg": 175, "peak_force": 620,
        "confidence": 0.75,
        "raw_zones": {"front": 10, "back": 620, "left": 20, "right": 15},
        "sig": "88cd092147beef19"
    }
]

def main():
    print("🪖 Helmet Edge Simulator — 20s Test", file=sys.stderr)
    print("📡 Listening for hits...", file=sys.stderr)
    
    start = time.time()
    for i, event in enumerate(EVENTS):
        delay = 3 + random.random() * 3  # 3-6s between events
        time.sleep(delay)
        
        # Update timestamps to be relative to test start
        event["timestamp_ms"] = int((time.time() - start) * 1000)
        event["seq"] = i + 1
        
        print(json.dumps(event), flush=True)
        print(f"  ⚡ Event {i+1}/{len(EVENTS)}: {event['event_type']} @ {event['primary_zone']}", file=sys.stderr)
    
    remaining = max(0, 20 - (time.time() - start))
    if remaining > 0:
        print(f"⏱️  Idle for {remaining:.1f}s...", file=sys.stderr)
        time.sleep(remaining)
    
    print("✅ Test complete", file=sys.stderr)

if __name__ == "__main__":
    main()
