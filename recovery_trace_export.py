from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Optional

from recovery_replay import replay_document
from recovery_trace_store import export_replay_document, latest_trace_session_id, list_trace_sessions


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export structured live RD6018 recovery traces into replay JSON."
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--session-id", help="Exact recovery trace session id")
    group.add_argument("--latest", action="store_true", help="Export the latest captured session")
    parser.add_argument("--list", action="store_true", help="List recent captured sessions")
    parser.add_argument("--limit", type=int, default=20, help="Session list limit")
    parser.add_argument("--output", "-o", help="Write replay JSON to this path")
    parser.add_argument(
        "--analyze",
        action="store_true",
        help="Run recovery_replay on the exported document and print the decision summary",
    )
    return parser


async def _resolve_session_id(explicit: Optional[str], latest: bool) -> str:
    if explicit:
        return explicit
    if latest:
        value = await latest_trace_session_id()
        if value:
            return value
        raise SystemExit("No captured recovery trace sessions found")
    raise SystemExit("Choose --session-id, --latest, or --list")


async def _main(args: argparse.Namespace) -> int:
    if args.list:
        sessions = await list_trace_sessions(limit=args.limit)
        print(json.dumps(sessions, ensure_ascii=False, indent=2, allow_nan=False))
        return 0

    session_id = await _resolve_session_id(args.session_id, args.latest)
    document = await export_replay_document(session_id)
    rendered = json.dumps(document, ensure_ascii=False, indent=2, allow_nan=False)

    if args.output:
        destination = Path(args.output)
        destination.write_text(rendered + "\n", encoding="utf-8")
        print(f"wrote {destination} ({document['trace_export']['replayable_samples']} replayable samples)")
    else:
        print(rendered)

    if args.analyze:
        result = replay_document(document)
        print(
            json.dumps(
                {
                    "decision_summary": result["decision_summary"],
                    "trend": result["trend"],
                },
                ensure_ascii=False,
                indent=2,
                allow_nan=False,
            )
        )
    return 0


def main() -> int:
    return asyncio.run(_main(_parser().parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
