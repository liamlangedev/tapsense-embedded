#!/usr/bin/env python3
"""TapSense v2 Raspberry Pi Consumer.

Polls the ESP8266 hub's store-and-forward /events endpoint over the FSR-Hub AP,
logs all helmet impacts and plate-carrier gesture events to JSONL, and forwards
actionable gesture dispatches (with attached helmet impact vector) to the
autonomous drone / C2 webhook.

Usage:
    python3 pi/tapsense_pi_client.py
    python3 pi/tapsense_pi_client.py --hub http://192.168.4.1 --drone-url http://127.0.0.1:9000/dispatch
    python3 pi/tapsense_pi_client.py --sim
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


def post_json(url: str, payload: dict, timeout: float = 2.0) -> bool:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return 200 <= resp.status < 300
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f"[drone-hook] forward failed: {exc}", file=sys.stderr, flush=True)
        return False


def format_event(ev: dict) -> str:
    kind = ev.get("kind", "?")
    etype = ev.get("event_type", "none")
    deg = ev.get("direction_deg", -1)
    card = ev.get("cardinal", "-")
    sev = ev.get("severity", "NONE")
    conf = ev.get("confidence", 0)
    if kind == "HELMET_IMPACT":
        return (
            f"#{ev.get('id')} HELMET_IMPACT dir={card} ({deg} deg) "
            f"peak={ev.get('peak_force')} sev={sev} conf={conf}%"
        )
    taps = ev.get("tap_count", 0)
    age = ev.get("impact_age_ms", -1)
    ctx = (
        f"attached_impact={card}({deg} deg, {sev}, {age}ms ago)"
        if deg >= 0
        else "no_prior_impact"
    )
    return f"#{ev.get('id')} GESTURE ({taps} taps) -> {etype} [{ctx}]"


def handle_event(ev: dict, log_path: Path, drone_url: str | None) -> None:
    print(format_event(ev), flush=True)
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(ev) + "\n")

    if (
        ev.get("kind") in ("GESTURE", "AUTO_ESCALATION")
        and ev.get("event_type")
        in (
            "critical_situation",
            "medical_supply_drone_request",
            "backup_resupply_request",
            "auto_medevac_unresponsive",
        )
    ):
        dispatch_payload = {
            "source": "tapsense_v2",
            "event_id": ev.get("id"),
            "mission_type": ev.get("event_type"),
            "tap_count": ev.get("tap_count"),
            "helmet_impact": {
                "direction_deg": ev.get("direction_deg"),
                "cardinal": ev.get("cardinal"),
                "severity": ev.get("severity"),
                "confidence": ev.get("confidence"),
                "age_ms": ev.get("impact_age_ms"),
            },
        }
        if drone_url:
            ok = post_json(drone_url, dispatch_payload)
            print(
                f"  -> drone dispatch {'ACK' if ok else 'QUEUED/FAILED'} ({drone_url})",
                flush=True,
            )
        else:
            print(f"  -> dispatch payload ready: {json.dumps(dispatch_payload)}", flush=True)


def run_sim(log_path: Path, drone_url: str | None) -> None:
    print("[sim] Running offline helmet-impact + plate-gesture sequence...", flush=True)
    demo_events = [
        {
            "id": 1,
            "ts_ms": 1420,
            "kind": "HELMET_IMPACT",
            "event_type": "helmet_impact_detected",
            "tap_count": 0,
            "direction_deg": 48,
            "cardinal": "NE",
            "peak_force": 512,
            "severity": "MEDIUM",
            "confidence": 87,
            "impact_age_ms": 0,
        },
        {
            "id": 2,
            "ts_ms": 3890,
            "kind": "GESTURE",
            "event_type": "medical_supply_drone_request",
            "tap_count": 3,
            "direction_deg": 48,
            "cardinal": "NE",
            "peak_force": 512,
            "severity": "MEDIUM",
            "confidence": 87,
            "impact_age_ms": 2470,
        },
    ]
    for ev in demo_events:
        handle_event(ev, log_path, drone_url)
        time.sleep(0.4)


def poll_loop(hub_url: str, interval_s: float, log_path: Path, drone_url: str | None) -> None:
    last_id = 0
    base = hub_url.rstrip("/")
    print(f"Polling {base}/events (interval={interval_s:.2f}s)", flush=True)
    while True:
        url = f"{base}/events?since={last_id}"
        try:
            with urllib.request.urlopen(url, timeout=1.5) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    for ev in data.get("events", []):
                        ev_id = int(ev.get("id", 0))
                        if ev_id > last_id:
                            last_id = ev_id
                        handle_event(ev, log_path, drone_url)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
            print(f"[wait] {base} unreachable ({exc}); retrying...", file=sys.stderr, flush=True)
        time.sleep(interval_s)


def main() -> None:
    ap = argparse.ArgumentParser(description="TapSense v2 Raspberry Pi event consumer")
    ap.add_argument("--hub", default="http://192.168.4.1", help="ESP8266 hub base URL")
    ap.add_argument("--interval", type=float, default=0.15, help="Poll interval in seconds")
    ap.add_argument("--log", default="tapsense_events.jsonl", help="Event log output file")
    ap.add_argument("--drone-url", default=None, help="Optional HTTP endpoint for drone dispatch")
    ap.add_argument("--sim", action="store_true", help="Run offline simulation sequence and exit")
    args = ap.parse_args()

    log_path = Path(args.log)
    if args.sim:
        run_sim(log_path, args.drone_url)
        return

    try:
        poll_loop(args.hub, args.interval, log_path, args.drone_url)
    except KeyboardInterrupt:
        print("\nStopped.", flush=True)


if __name__ == "__main__":
    main()
