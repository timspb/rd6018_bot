#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
import tempfile
import time
from dataclasses import asdict
from typing import Any

from config import ENTITY_MAP, HA_TOKEN, HA_URL
from ha_history import HomeAssistantHistoryError, HomeAssistantHistoryReader
from hass_api import HassClient


STATE_VERSION = 1


def _binary(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if value == 1:
            return True
        if value == 0:
            return False
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"on", "true", "1"}:
            return True
        if normalized in {"off", "false", "0"}:
            return False
    return None


def _write_hands_off_state(path: str) -> None:
    absolute = os.path.abspath(path)
    directory = os.path.dirname(absolute) or "."
    os.makedirs(directory, exist_ok=True)
    document = {
        "version": STATE_VERSION,
        "mode": "hands_off",
        "updated_at": time.time(),
        "prepared_by": "tools/prepare_hands_off_live_session.py",
    }
    fd, tmp_path = tempfile.mkstemp(
        prefix=".rd-control-mode-live-preflight-",
        suffix=".tmp",
        dir=directory,
        text=True,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(document, handle, ensure_ascii=False, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, absolute)
        try:
            dir_fd = os.open(directory, os.O_RDONLY)
        except OSError:
            dir_fd = None
        if dir_fd is not None:
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
    finally:
        try:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
        except OSError:
            pass


async def run(args: argparse.Namespace) -> int:
    if not HA_URL or not HA_TOKEN:
        raise RuntimeError("HA_URL/HA_TOKEN are required")

    hass = HassClient(HA_URL, HA_TOKEN)
    try:
        live = await hass.get_all_live()
        output = _binary(live.get("switch"))
        if output is not True:
            raise RuntimeError(
                "refusing live-session HANDS_OFF bootstrap: current RD6018 Output is not positively ON"
            )

        required = ("set_voltage", "set_current", "ovp", "ocp")
        missing = [key for key in required if live.get(key) in (None, "", "unknown", "unavailable")]
        if missing:
            raise RuntimeError(
                "refusing live-session HANDS_OFF bootstrap: missing live readback "
                + ", ".join(missing)
            )

        reader = HomeAssistantHistoryReader(hass, ENTITY_MAP)
        try:
            history = await reader.read_mix_evidence(
                live=live,
                lookback_s=max(1.0, float(args.lookback_hours) * 3600.0),
            )
            history_payload = asdict(history)
            history_error = ""
        except HomeAssistantHistoryError as exc:
            history_payload = None
            history_error = str(exc)

        report = {
            "output": live.get("switch"),
            "battery_voltage": live.get("battery_voltage"),
            "output_voltage": live.get("voltage"),
            "current": live.get("current"),
            "temp_ext": live.get("temp_ext_v2", live.get("temp_ext")),
            "set_voltage": live.get("set_voltage"),
            "set_current": live.get("set_current"),
            "ovp": live.get("ovp"),
            "ocp": live.get("ocp"),
            "history": history_payload,
            "history_error": history_error,
            "state_file": os.path.abspath(args.state_file),
            "hardware_mutated": False,
        }

        if not args.dry_run:
            _write_hands_off_state(args.state_file)
            report["prepared_mode"] = "hands_off"
        else:
            report["prepared_mode"] = None

        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    finally:
        await hass.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare a deliberate HANDS_OFF bootstrap before starting the V2 bot over "
            "an already-running external RD6018 session. Reads HA/Recorder only; never "
            "writes RD6018 Output or setpoints."
        )
    )
    parser.add_argument(
        "--state-file",
        default="rd_control_mode_v2.json",
        help="persistent RD control-mode file used by bot.py",
    )
    parser.add_argument(
        "--lookback-hours",
        type=float,
        default=168.0,
        help="HA Recorder lookback used only for context (default: 7 days)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="read/validate/report without writing HANDS_OFF state",
    )
    args = parser.parse_args()
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
