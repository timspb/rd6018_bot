#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bench_capture import capture_dynamic_loop_phase  # noqa: E402
from hass_api import HassClient  # noqa: E402


async def _run(args: argparse.Namespace) -> int:
    if args.truncate:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text("", encoding="utf-8")

    client = HassClient()
    try:
        summary = await capture_dynamic_loop_phase(
            client,
            args.output,
            phase=args.phase,
            connection_id=args.connection_id,
            duration_s=args.duration_s,
            poll_interval_s=args.poll_s,
        )
    except (OSError, TypeError, ValueError) as exc:
        print(f"capture failed: {exc}", file=sys.stderr)
        return 2
    finally:
        await client.close()

    print(
        json.dumps(
            {
                "output": str(args.output),
                "phase": args.phase,
                "connection_id": args.connection_id,
                "written": summary.written,
                "duplicate_polls": summary.duplicate_polls,
                "invalid_polls": summary.invalid_polls,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if summary.written > 0 else 3


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Capture read-only RD6018/Home Assistant observations for dynamic-loop "
            "bench characterization. This tool never changes voltage, current or output state."
        )
    )
    parser.add_argument("output", type=Path, help="JSONL file to append observations to")
    parser.add_argument("--phase", required=True, help="operator phase label, e.g. baseline/stepped/restored")
    parser.add_argument("--connection-id", required=True, help="identity of the unchanged physical lead/clip setup")
    parser.add_argument("--duration-s", required=True, type=float, help="capture wall-clock duration in seconds")
    parser.add_argument("--poll-s", type=float, default=0.5, help="HA polling cadence; duplicate source samples are discarded")
    parser.add_argument("--truncate", action="store_true", help="clear output before this phase")
    args = parser.parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
