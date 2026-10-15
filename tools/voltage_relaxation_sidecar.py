"""Read-only, out-of-process SAFE_WAIT voltage relaxation collector for node104.

This optional worker never imports charging executors or issues control commands.
It shares only the existing HA telemetry endpoint and a read-only session file
with the production bot. Its SQLite journal is a separate database.
"""
from __future__ import annotations

import asyncio
import fcntl
import json
import logging
import os
from pathlib import Path
import time
from typing import Any, Mapping

try:  # Repository import during local tests
    from runtime.charge.observability.voltage_relaxation import VoltageRelaxationRecorder
except ModuleNotFoundError:  # Optional self-contained deployment next to this file
    from voltage_relaxation import VoltageRelaxationRecorder

LOG = logging.getLogger("rd6018.voltage_relaxation")
STATE_PATH = Path(os.environ.get("D063_STATE_DIR", "/opt/services/rd6018-bot/state"))
SESSION_FILE = STATE_PATH / "charge_session.json"
DATABASE = STATE_PATH / "voltage_relaxation.db"
LOCK_FILE = STATE_PATH / ".voltage_relaxation.lock"
INTERVAL_S = 30.0
MAX_SESSION_FILE_AGE_S = 600.0
SAFE_WAIT_STAGE = "Безопасное ожидание"
PROFILE_NAMES = frozenset(("Ca/Ca", "EFB"))


def validated_session(
    document: Any, *, file_mtime_s: float, observed_at_s: float
) -> dict[str, Any] | None:
    """Accept only durable, fresh, session-bound SAFE_WAIT evidence.

    A missing/stale/corrupt file means no authoritative stage and NO sample.
    The observer does not guess stage from voltage or an absent session file.
    """
    if not isinstance(document, Mapping) or not (
        0 <= observed_at_s - file_mtime_s <= MAX_SESSION_FILE_AGE_S
    ):
        return None
    if document.get("stage") != SAFE_WAIT_STAGE or document.get("profile") not in PROFILE_NAMES:
        return None
    session_id = document.get("v2_trace_session_id")
    if not isinstance(session_id, str) or not session_id:
        return None
    start = document.get("safe_wait_start")
    try:
        if isinstance(start, bool):
            return None
        start_s = float(start)
    except (ValueError, TypeError, OverflowError):
        return None
    if not 0 < start_s <= observed_at_s:
        return None
    next_stage = document.get("safe_wait_next_stage")
    if next_stage not in ("Main Charge", "Done"):
        return None
    return {
        "stage": SAFE_WAIT_STAGE,
        "session_id": session_id,
        "battery_id": document.get("v2_battery_id"),
        "profile": document["profile"],
        "safe_wait_epoch_s": start_s,
        "continuation": "MAIN" if next_stage == "Main Charge" else "DONE",
    }


def read_session(path: Path, *, now_s: float) -> dict[str, Any] | None:
    try:
        stat = path.stat()
        if stat.st_size > 1024 * 1024:
            return None
        document = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, UnicodeError, ValueError):
        return None
    return validated_session(document, file_mtime_s=stat.st_mtime, observed_at_s=now_s)


class PassiveCollector:
    def __init__(self, *, session_file: Path = SESSION_FILE):
        self.session_file = session_file
        self.recorder = VoltageRelaxationRecorder()

    async def poll(self, db: Any, hass: Any, *, now_s: float) -> dict[str, Any]:
        state = read_session(self.session_file, now_s=now_s)
        if state is None:
            await self.recorder.observe(
                db, live={}, stage="", safe_wait_stage=SAFE_WAIT_STAGE,
                session_id=None, battery_id=None, profile="",
                safe_wait_epoch_s=None, continuation=None, observed_at_s=now_s,
            )
            return {"status": "no_eligible_safe_wait"}
        try:
            live = await hass.get_all_live()
        except Exception as exc:
            LOG.warning("Read-only telemetry unavailable: %s", type(exc).__name__)
            # Unknown current Output is not assumed OFF. Close current segment.
            await self.recorder.observe(
                db, live={}, stage="", safe_wait_stage=SAFE_WAIT_STAGE,
                session_id=None, battery_id=None, profile="",
                safe_wait_epoch_s=None, continuation=None, observed_at_s=now_s,
            )
            return {"status": "telemetry_unavailable"}
        result = await self.recorder.observe(
            db, live=live, stage=state["stage"], safe_wait_stage=SAFE_WAIT_STAGE,
            session_id=state["session_id"], battery_id=state["battery_id"],
            profile=state["profile"], safe_wait_epoch_s=state["safe_wait_epoch_s"],
            continuation=state["continuation"], observed_at_s=now_s,
        )
        if result is None:
            return {"status": "no_fresh_off_evidence"}
        return {
            "status": "sample_written", "sample_count": result["samples"],
            "complete_windows": [
                key for key, metric in result["signature"].items()
                if key.startswith("relax_") and isinstance(metric, dict)
                and metric.get("status") == "measured"
            ],
        }


async def serve(*, once: bool = False) -> None:
    import aiosqlite
    from config import HA_TOKEN, HA_URL
    from hass_api import HassClient

    if not HA_URL or not HA_TOKEN:
        raise RuntimeError("existing HA configuration unavailable")
    STATE_PATH.mkdir(parents=True, exist_ok=True)
    with LOCK_FILE.open("a+") as lock_fd:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("voltage-relaxation worker already active") from None
        ha = HassClient(HA_URL, HA_TOKEN)
        async with aiosqlite.connect(DATABASE, timeout=7) as db:
            collector = PassiveCollector()
            try:
                while True:
                    try:
                        result = await collector.poll(db, ha, now_s=time.time())
                        LOG.info("D063 observer: %s", result)
                    except Exception as exc:
                        # Do not affect the production bot, even if our own DB fails.
                        LOG.error("D063 poll failed: %s", type(exc).__name__)
                        if once:
                            raise
                    if once:
                        break
                    await asyncio.sleep(INTERVAL_S)
            finally:
                await ha.close()


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Passive RD6018 SAFE_WAIT observer")
    parser.add_argument("--once", action="store_true", help="single pass, for commissioning")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    asyncio.run(serve(once=args.once))


if __name__ == "__main__":
    main()
