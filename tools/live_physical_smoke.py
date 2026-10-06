from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runtime.bench.live import LiveSmokeRunner
from runtime.config import load_config


def _snapshot(value):
    if value is None:
        return None
    data = asdict(value)
    return {
        "connection_state": data["connection_state"],
        "output_state": data["output_state"],
        "measured_voltage": data["measured_voltage"],
        "measured_current": data["measured_current"],
        "configured_voltage": data["configured_voltage"],
        "configured_current": data["configured_current"],
        "ovp": data["ovp"],
        "ocp": data["ocp"],
        "temperature": data["temperature"],
        "battery_voltage": data["battery_voltage"],
    }


def _payload(evidence):
    runs = [
        {
            "transport": item.transport,
            "quality": item.quality,
            "errors": list(item.errors),
        }
        for item in evidence.runs
    ]
    passed = (
        evidence.comparison.status == "MATCH"
        and all(item["quality"] == "VALID" for item in runs)
    )
    return {
        "status": "PASS" if passed else "BLOCKED",
        "operator": evidence.operator,
        "comparison": {
            "status": evidence.comparison.status,
            "fields": list(evidence.comparison.fields),
            "reason": evidence.comparison.reason,
        },
        "ha102": _snapshot(evidence.ha_snapshot),
        "esp128": _snapshot(evidence.esp_snapshot),
        "runs": runs,
    }


async def _run(operator: str, config_root: str) -> int:
    try:
        config = load_config(config_root)
        evidence = await LiveSmokeRunner(config).run(operator)
        payload = _payload(evidence)
    except Exception as exc:
        payload = {
            "status": "BLOCKED",
            "operator": operator,
            "error": f"{type(exc).__name__}: {exc}",
        }
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0 if payload["status"] == "PASS" else 2


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Strictly read-only HA102/ESP128 physical smoke evidence"
    )
    parser.add_argument("--operator", default="live-smoke")
    parser.add_argument("--config-root", default="config")
    args = parser.parse_args()
    return asyncio.run(_run(args.operator, args.config_root))


if __name__ == "__main__":
    raise SystemExit(main())
