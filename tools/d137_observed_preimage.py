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
import time

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
    tracked = [journal_path, marker, quarantine_path]
    if any(p.is_symlink() or not p.is_file() for p in tracked):
        raise ValueError("unsafe or absent durable state")
    if session_path.is_symlink():
        raise ValueError("unsafe session symlink")
    session_present = session_path.is_file()
    if session_path.exists() and not session_present:
        raise ValueError("unsafe session path")
    if session_present:
        tracked.append(session_path)
    before = {str(p): sha256(p) for p in tracked}
    argv = (Path("/proc") / str(pid) / "cmdline").read_bytes().split(bytes([0]))
    if str(app / "bot.py").encode() not in argv:
        raise ValueError("process does not run the installed application")
    session = read_small_json(session_path) if session_present else None
    quarantine = read_small_json(quarantine_path)
    journal = read_small_json(journal_path)
    retirement = quarantine.get("retirement")
    preserved_guard = None
    if session_present and session.get("stage") == "Main Charge":
        # A live guarded MAIN session may be preserved across a software-only
        # restart while the independent D091 Native/HA proof confirms Output
        # OFF. Bind every persisted byte and validate the canonical guard
        # snapshot; never turn the snapshot into permission to resume charging.
        if (session.get("v2_authoritative") is not True
                or type(session.get("v2_trace_session_id")) is not str
                or not session["v2_trace_session_id"].strip()
                or type(session.get("v2_battery_id")) is not str
                or not session["v2_battery_id"].strip()
                or str(session.get("profile", "")).upper() not in {"EFB", "CA/CA"}
                or type(session.get("ah_limit")) not in (int, float)
                or session["ah_limit"] <= 0):
            raise ValueError("active guarded MAIN session identity is invalid")
        retirement_keys = {"operator_id", "session_id", "confirmed_off_evidence",
                           "retired_utc", "incident_id", "incident_reason", "battery_id"}
        if (not isinstance(retirement, dict)
                or set(quarantine) != {"owner", "schema_version", "state", "quarantined", "retirement"}
                or set(retirement) != retirement_keys
                or any(type(retirement.get(k)) is not str or not retirement[k].strip()
                       for k in ("operator_id", "session_id", "confirmed_off_evidence",
                                 "retired_utc", "incident_id", "incident_reason"))
                or (retirement["battery_id"] is not None and
                    (type(retirement["battery_id"]) is not str or not retirement["battery_id"].strip()))
                or quarantine.get("owner") != "runtime.charge.recovery_quarantine_journal"
                or quarantine.get("schema_version") != 2
                or quarantine.get("state") != "retired"
                or quarantine.get("quarantined") is not False
                or not isinstance(retirement, dict)):
            raise ValueError("state-preserving MAIN admission requires canonical clear quarantine")
        try:
            try:
                from runtime.charge.strategy.main_guard_session import GUARD_KEY, read_guard
            except ModuleNotFoundError:
                from main_guard_session import GUARD_KEY, read_guard
            guard, revision = read_guard(
                session, session_id=session["v2_trace_session_id"],
                battery_id=session["v2_battery_id"], now_s=time.time())
        except Exception as exc:
            raise ValueError("active MAIN canonical guard failed integrity/identity validation") from exc
        if (revision <= 0 or guard.pending is not None or guard.fault is not None
                or guard.last_output_on is not False or guard.last_stage_main is not True
                or abs(guard.capacity_ah - float(session["ah_limit"])) > 1e-6):
            raise ValueError("active MAIN guard is pending, faulted, or not state-preserving OFF")
        guard_record = session[GUARD_KEY]
        preserved_guard = {"session_id": guard.session_id,
                           "battery_id": guard.battery_id,
                           "revision": revision,
                           "guard_sha256": guard_record["sha256"],
                           "guard_snapshot_sha256": hashlib.sha256(json.dumps(
                               guard_record["snapshot"], sort_keys=True,
                               separators=(",", ":"), ensure_ascii=True,
                               allow_nan=False).encode("ascii")).hexdigest()}
    elif not isinstance(retirement, dict) or quarantine.get("quarantined") is not False:
        raise ValueError("durable retirement and verified-OFF identity do not agree")
    elif session_present:
        if (session.get("state") != "retired" or session.get("stage") != "RETIRED"
                or retirement.get("session_id") != session.get("session_id")
                or retirement.get("confirmed_off_evidence") != session.get("verified_off_transaction_id")):
            raise ValueError("durable retirement and verified-OFF identity do not agree")
    else:
        # The canonical controller can retire an old managed session and later
        # remove charge_session.json. Observe this fact directly; never create
        # a fake tombstone. Physical Output OFF is independently assessed by
        # the existing D142/D091 owner before any service stop.
        if (quarantine.get("schema_version") != 2
                or quarantine.get("state") != "retired"
                or quarantine.get("owner") != "runtime.charge.recovery_quarantine_journal"
                or not isinstance(retirement.get("session_id"), str)
                or not retirement["session_id"].strip()
                or not isinstance(retirement.get("confirmed_off_evidence"), str)
                or not retirement["confirmed_off_evidence"].strip()
                or not isinstance(retirement.get("retired_utc"), str)
                or not retirement["retired_utc"].strip()):
            raise ValueError("missing-session retirement record is not authentic")
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
        "retired_session": (None if preserved_guard else {
            "session_id": session.get("session_id") if session_present else retirement["session_id"],
            "off_evidence": (session.get("verified_off_transaction_id")
                             if session_present else retirement["confirmed_off_evidence"]),
            "session_sha256": before[str(session_path)] if session_present else None,
            "session_absent": not session_present,
            "quarantine_sha256": before[str(quarantine_path)]
        }),
        "preserved_guarded_main": ({
            **preserved_guard,
            "session_sha256": before[str(session_path)],
            "quarantine_sha256": before[str(quarantine_path)],
            "automatic_resume_authorized": False,
        } if preserved_guard else None)
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
