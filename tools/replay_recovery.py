#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow running as `python tools/replay_recovery.py trace.json` from repo root.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from recovery_replay import replay_json_file  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Replay RD6018 Pb recovery U/I/T traces and calculate cycle evidence/trend."
    )
    parser.add_argument("trace", help="JSON document containing one or more recovery cycles")
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="pretty-print JSON output",
    )
    args = parser.parse_args()

    try:
        result = replay_json_file(args.trace)
    except (OSError, ValueError, json.JSONDecodeError, KeyError, TypeError) as exc:
        print(f"replay failed: {exc}", file=sys.stderr)
        return 2

    if args.pretty:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
