"""Local-only queueing service; outbound delivery stays disabled without API."""
from __future__ import annotations

import argparse
import json
import os
import signal
import time
from pathlib import Path

from connector import Event, Outbox, load_config, normalize_snapshot, validate_route


def read_snapshot(path: Path) -> dict:
    if path.is_symlink() or not path.is_file():
        raise ValueError("snapshot must be a regular non-symlink file")
    if path.stat().st_size > 65536:
        raise ValueError("snapshot exceeds size limit")
    return json.loads(path.read_text(encoding="utf-8"))


def run(config_path: Path, once: bool = False) -> int:
    config = load_config(config_path)
    route = config["route"]
    if route is not None:
        validate_route(route)
    outbox = Outbox(Path(config["outbox_path"]))
    previous: dict | None = None
    last_heartbeat = 0.0
    last_good = 0.0
    stale_latched = False
    stopping = False

    def stop(_signum, _frame):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        while not stopping:
            now = time.time()
            try:
                snapshot = read_snapshot(Path(config["source_snapshot"]))
                events, previous = normalize_snapshot(snapshot, previous, now,
                                                      config["stale_after_s"])
                if stale_latched:
                    events.append(Event.create("telemetry_recovered", "source", now,
                                               "connector_timer", {"service_state": "running"}))
                    stale_latched = False
                last_good = now
                for event in events:
                    outbox.enqueue(event, now)
                if now - last_heartbeat >= config["heartbeat_interval_s"]:
                    heartbeat_slot = int(now // config["heartbeat_interval_s"])
                    outbox.enqueue(Event.create("heartbeat", f"periodic:{heartbeat_slot}", now,
                                                "connector_timer", {"service_state": "running"}), now)
                    last_heartbeat = now
            except (OSError, ValueError, json.JSONDecodeError):
                # Source errors are isolated; never turn source failure into a charger action.
                if last_good and now - last_good > config["stale_after_s"] and not stale_latched:
                    stale = Event.create("telemetry_stale", "source", now,
                                         "connector_timer", {"freshness_s": now - last_good}, "warning")
                    outbox.enqueue(stale, now)
                    stale_latched = True
            if once:
                break
            time.sleep(config["poll_interval_s"])
    finally:
        outbox.close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--once", action="store_true", help="one local read-only snapshot and queue pass")
    args = parser.parse_args()
    return run(args.config, args.once)


if __name__ == "__main__":
    raise SystemExit(main())
