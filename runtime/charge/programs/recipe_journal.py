"""Append-only per-run experiment ledger; independent of legacy charge logs."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def append_event(path: str | Path, *, session_id: str, recipe_id: str,
                 version: int, digest: str, event: str,
                 action_id: str | None = None, detail: str = "") -> None:
    if not session_id or not recipe_id or not digest:
        raise ValueError("journal identity required")
    if event not in {"PENDING", "VERIFIED", "UNVERIFIED", "INTERRUPTED", "COMPLETE"}:
        raise ValueError("unsupported journal event")
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    record: dict[str, Any] = {
        "session": session_id, "recipe": recipe_id, "version": version,
        "digest": digest, "event": event, "action_id": action_id, "detail": detail,
    }
    with target.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        f.flush()
        os.fsync(f.fileno())


def read_events(path: str | Path) -> list[dict[str, Any]]:
    with Path(path).open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]
