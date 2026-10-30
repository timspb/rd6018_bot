"""D137 composite observed preimage for future independent software release.

Produces a read-only, *candidate-free* observed preimage record. It never
modifies the original D090 journal, install marker, bot, state or actuator.
It is not an approval to roll back the old D090 STARTED transaction.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

try:
    from tools.d133_live_byte_baseline import tree_manifest, read_small_json, sha256
    from tools.d136_observed_venv import inventory as venv_inventory
except ModuleNotFoundError:
    from d133_live_byte_baseline import tree_manifest, read_small_json, sha256
    from d136_observed_venv import inventory as venv_inventory


def observed_preimage(root: Path, *, pid: int) -> dict[str, object]:
    if not isinstance(pid, int) or pid <= 0 or root.is_symlink() or not root.is_dir():
        raise ValueError("invalid root or process ID")
    app = root / "app"
    venv = root / "venv"
    journal_path = root / "D090_TRANSACTION.json"
    marker = root / ".deploy_sha"
    session_path = root / "state" / "charge_session.json"
    quarantine_path = root / "state" / "session_recovery_quarantine.json"
    tracked = [journal_path, marker, session_path, quarantine_path]
    if any(p.is_symlink() or not p.is_file() for p in tracked):
        raise ValueError("unsafe or absent durable state")
    before = {str(p): sha256(p) for p in tracked}
    argv = (Path("/proc") / str(pid) / "cmdline").read_bytes().split(bytes([0]))
    if str(app / "bot.py").encode() not in argv:
        raise ValueError("process does not run the installed application")
    session = read_small_json(session_path)
    quarantine = read_small_json(quarantine_path)
    journal = read_small_json(journal_path)
    retirement = quarantine.get("retirement")
    if (session.get("state") != "retired" or session.get("stage") != "RETIRED"
            or quarantine.get("quarantined") is not False
            or not isinstance(retirement, dict)
            or retirement.get("session_id") != session.get("session_id")
            or retirement.get("confirmed_off_evidence") != session.get("verified_off_transaction_id")):
        raise ValueError("durable retirement and verified-OFF identity do not agree")
    if (journal.get("phase") != "STARTED"
            or isinstance(journal.get("candidate_inventory"), dict)):
        raise ValueError("unexpected historical D090 transaction state")
    app1 = tree_manifest(app)
    venv1 = venv_inventory(venv)
    app2 = tree_manifest(app)
    venv2 = venv_inventory(venv)
    if app1 != app2 or venv1 != venv2:
        raise RuntimeError("installed bytes changed during observation")
    if any(sha256(p) != before[str(p)] for p in tracked):
        raise RuntimeError("durable state changed during observation")
    argv2 = (Path("/proc") / str(pid) / "cmdline").read_bytes().split(bytes([0]))
    if argv != argv2:
        raise RuntimeError("process identity changed during observation")
    payload = {
        "schema": "D137_OBSERVED_PREIMAGE_V1",
        "phase": "OBSERVED_PREIMAGE",
        "candidate": None,
        "admitted": False,
        "root": str(root),
        "process": {"pid": pid, "entrypoint": str(app / "bot.py")},
        "installed_app": app2,
        "installed_venv": venv2,
        "d090": {
            "transaction": journal.get("transaction"),
            "phase": journal.get("phase"),
            "journal_sha256": before[str(journal_path)],
            "marker_sha256": before[str(marker)],
            "candidate_inventory_present": False
        },
        "retired_session": {
            "session_id": session.get("session_id"),
            "off_evidence": session.get("verified_off_transaction_id"),
            "session_sha256": before[str(session_path)],
            "quarantine_sha256": before[str(quarantine_path)]
        }
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    payload["preimage_sha256"] = hashlib.sha256(canonical.encode("ascii")).hexdigest()
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("/opt/services/rd6018-bot"))
    parser.add_argument("--pid", type=int, required=True)
    args = parser.parse_args()
    print(json.dumps(observed_preimage(args.root, pid=args.pid), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
