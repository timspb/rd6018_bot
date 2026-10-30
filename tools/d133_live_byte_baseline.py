"""D133 read-only inventory of installed RD6018 bytes and deployment ledger.

No service commands, output actuation, state mutation, or secret disclosure.
Run through the ordinary Python interpreter (never via D090 recover).
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
import sys

DEFAULT_ROOT = Path("/opt/services/rd6018-bot")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tree_manifest(root: Path) -> dict[str, object]:
    if root.is_symlink() or not root.is_dir():
        raise ValueError("app directory missing or symlinked")
    entries: list[dict[str, object]] = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if any(part in ("__pycache__", ".git", ".pytest_cache") for part in path.relative_to(root).parts):
            continue
        if path.is_symlink():
            raise ValueError("symlink in installed application: " + relative)
        if path.is_dir():
            continue
        if not path.is_file():
            raise ValueError("special file in application: " + relative)
        item = {"path": relative, "size": path.stat().st_size, "sha256": sha256(path),
                "executable": bool(path.stat().st_mode & stat.S_IXUSR)}
        entries.append(item)
    canonical = json.dumps(entries, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return {"files": len(entries), "tree_sha256": hashlib.sha256(canonical.encode()).hexdigest()}


def read_small_json(path: Path) -> dict[str, object]:
    if path.is_symlink() or path.stat().st_size > 16 * 1024 * 1024:
        raise ValueError("unsafe JSON source")
    result = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(result, dict):
        raise ValueError("JSON must be an object")
    return result


def inspect(root: Path, *, pid: int | None = None) -> dict[str, object]:
    if root.is_symlink() or not root.is_dir():
        raise ValueError("invalid installation root")
    transaction = read_small_json(root / "D090_TRANSACTION.json")
    session = read_small_json(root / "state/charge_session.json")
    quarantine = read_small_json(root / "state/session_recovery_quarantine.json")
    marker = root / ".deploy_sha"
    if marker.is_symlink() or not marker.is_file():
        raise ValueError("invalid deployment marker")
    marker_text = marker.read_text(encoding="ascii").strip()
    if not (len(marker_text) == 40 and all(c in "0123456789abcdef" for c in marker_text)):
        raise ValueError("invalid legacy marker")
    pid_identity = None
    if pid is not None:
        if not isinstance(pid, int) or pid <= 0:
            raise ValueError("invalid PID")
        cmdline = (Path("/proc") / str(pid) / "cmdline").read_bytes().split(b"\\0")
        expected = str(root / "app/bot.py").encode()
        pid_identity = {"pid": pid, "entrypoint_match": expected in cmdline}
        if not pid_identity["entrypoint_match"]:
            raise ValueError("service PID is not running the installed entrypoint")
    inventory = tree_manifest(root / "app")
    retired = session.get("state") == "retired" and session.get("stage") == "RETIRED"
    retirement = quarantine.get("retirement")
    matching = (isinstance(retirement, dict) and session.get("session_id") == retirement.get("session_id")
                and session.get("verified_off_transaction_id") == retirement.get("confirmed_off_evidence"))
    result = {
        "schema": "D133_READONLY_BASELINE_V1",
        "root": str(root),
        "installed_app": inventory,
        "service": pid_identity,
        "deployment": {"marker": marker_text, "marker_sha256": sha256(marker),
                       "d090_phase": transaction.get("phase"), "d090_transaction": transaction.get("transaction"),
                       "source_sha": transaction.get("source_sha"),
                       "candidate_inventory_present": isinstance(transaction.get("candidate_inventory"), dict)},
        "session": {"retired": retired, "session_id": session.get("session_id"),
                    "quarantined": quarantine.get("quarantined"), "retirement_evidence_matches": bool(matching)},
        "sidecar": {"d090_cli_sha256": sha256(root / "d090/node104_d090_transaction.py")},
    }
    return result


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--pid", type=int)
    args = parser.parse_args()
    print(json.dumps(inspect(args.root, pid=args.pid), indent=2, ensure_ascii=True, sort_keys=True))


if __name__ == "__main__":
    main()
