"""Read-only HA source adapter and local event spool runner.

Only the isolated GET-only HA client is instantiated. No controls are available.
"""
from __future__ import annotations

import argparse
import signal
import time
from pathlib import Path

from connector import EventEnvelope, Outbox, load_config, normalize_snapshot
from ha_source import HAConfig, HAReadOnlyClient, SourceError, load_entity_allowlist


def run(config_path: Path, once: bool = False) -> int:
    config = load_config(config_path)
    ha_config = HAConfig.from_env()
    entities = load_entity_allowlist(Path(config["entity_config"]))
    source = HAReadOnlyClient(ha_config, entities, session_path=Path(config["session_path"]),
                              session_max_age_s=config["session_max_age_s"])
    outbox = Outbox(Path(config["outbox_path"]), config["max_events"], config["max_age_s"])
    previous = outbox.load_state()
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
                snapshot = source.read_snapshot(now=now)
                events, current = normalize_snapshot(snapshot, previous, now, config["stale_after_s"])
                for event in events:
                    outbox.enqueue(event, now)
                previous = current
                outbox.save_state(previous)
                slot = int(now // config["heartbeat_interval_s"])
                outbox.enqueue(EventEnvelope.for_occurrence(
                    "charger.heartbeat", f"heartbeat:{slot}", now,
                    {"freshness_s": snapshot.freshness_s,
                     "freshness_known": snapshot.freshness_known}), now)
            except (OSError, SourceError, ValueError):
                was_unknown = bool(previous and previous.get("freshness_unknown"))
                failure_started_at = (previous or {}).get("source_failure_started_at", now)
                if not was_unknown:
                    outbox.enqueue(EventEnvelope.for_occurrence(
                        "charger.telemetry_unknown", f"source-unavailable:{failure_started_at}",
                        now, {"freshness_known": False}, "warning"), now)
                previous = dict(previous or {})
                previous.update({"stale": False, "freshness_unknown": True,
                                 "source_failure_started_at": failure_started_at})
                outbox.save_state(previous)
            if once:
                break
            time.sleep(config["poll_interval_s"])
    finally:
        outbox.close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--once", action="store_true", help="one local snapshot and spool pass")
    args = parser.parse_args()
    return run(args.config, args.once)


if __name__ == "__main__":
    raise SystemExit(main())
