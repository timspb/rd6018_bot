"""D137 composite observed preimage for future independent software release.

Produces a read-only, *candidate-free* observed preimage record. It never
modifies the original D090 journal, install marker, bot, state or actuator.
It is not an approval to roll back the old D090 STARTED transaction.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import time

try:
    from tools.d133_live_byte_baseline import tree_manifest, read_small_json, sha256
    from tools.d136_observed_venv import inventory as venv_inventory
except ModuleNotFoundError:
    from d133_live_byte_baseline import tree_manifest, read_small_json, sha256
    from d136_observed_venv import inventory as venv_inventory


def observed_preimage(root: Path, *, pid: int,
                      physical_off_reconciliation: dict[str, object] | None = None) -> dict[str, object]:
    if not isinstance(pid, int) or pid <= 0 or root.is_symlink() or not root.is_dir():
        raise ValueError("invalid root or process ID")
    app = root / "app"
    venv = root / "venv"
    journal_path = root / "D090_TRANSACTION.json"
    marker = root / ".deploy_sha"
    session_path = root / "state" / "charge_session.json"
    quarantine_path = root / "state" / "session_recovery_quarantine.json"
    tracked = [journal_path, quarantine_path]
    if any(p.is_symlink() or not p.is_file() for p in tracked):
        raise ValueError("unsafe or absent durable state")
    marker_present = marker.exists()
    if marker.is_symlink() or (marker_present and not marker.is_file()):
        raise ValueError("unsafe deployment marker")
    if marker_present:
        tracked.append(marker)
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
    d144_identity = None
    if not marker_present:
        # D144 is the canonical release identity after a state-preserving
        # install. Historical transaction slots may have been pruned by
        # ordinary cleanup; pin the newest surviving COMMITTED slot instead.
        # Verify every installed source file against its candidate manifest.
        from tools.node104_d090_transaction import inventory as installed_app_inventory

        slots = []
        for transaction_path in root.glob("D144_TRANSACTION*.json"):
            if transaction_path.is_symlink() or not transaction_path.is_file():
                raise ValueError("unsafe D144 installed release history")
            name = transaction_path.name
            if name == "D144_TRANSACTION.json":
                slot = 1
            else:
                suffix = name.removeprefix("D144_TRANSACTION_").removesuffix(".json")
                if not suffix.isdigit() or str(int(suffix)) != suffix:
                    raise ValueError("unknown D144 installed release history")
                slot = int(suffix)
            slots.append((slot, transaction_path))
        if not slots or len({slot for slot, _ in slots}) != len(slots):
            raise ValueError("D144 installed release history is absent or ambiguous")
        committed = []
        known_slots = {slot for slot, _ in slots}
        for identity_candidate in root.glob("D144_INSTALLED_RELEASE*.json"):
            if identity_candidate.is_symlink() or not identity_candidate.is_file():
                raise ValueError("unsafe D144 installed release history")
            suffix = identity_candidate.name.removeprefix("D144_INSTALLED_RELEASE").removesuffix(".json")
            if suffix == "":
                identity_slot = 1
            elif suffix.startswith("_") and suffix[1:].isdigit() and str(int(suffix[1:])) == suffix[1:]:
                identity_slot = int(suffix[1:])
            else:
                raise ValueError("unknown D144 installed release identity history")
            if identity_slot not in known_slots:
                raise ValueError("D144 installed release identity is ambiguous")
        for slot, transaction_path in slots:
            transaction = read_small_json(transaction_path)
            phase = transaction.get("phase")
            if phase in {"RESTORED", "FAILED", "PREPARED"}:
                continue
            if phase != "COMMITTED":
                raise ValueError("D144 installed release history has ambiguous phase")
            suffix = "" if slot == 1 else "_" + str(slot)
            identity_path = root / ("D144_INSTALLED_RELEASE" + suffix + ".json")
            if identity_path.is_symlink() or not identity_path.is_file():
                raise ValueError("D144 committed installed release identity is absent or unsafe")
            identity = read_small_json(identity_path)
            release = transaction.get("release_identity")
            if (not isinstance(release, dict)
                    or identity.get("transaction") != transaction.get("transaction")
                    or {k: identity.get(k) for k in
                        ("schema", "source_sha", "candidate_identity_sha256")} != release):
                raise ValueError("D144 committed installed release identity is ambiguous")
            committed.append((slot, transaction_path, identity_path, transaction))
        if not committed:
            raise ValueError("D144 committed installed release identity is absent or unsafe")
        slot, transaction_path, identity_path, transaction = max(committed, key=lambda item: item[0])
        tracked.extend((transaction_path, identity_path))
        before.update({str(p): sha256(p) for p in (transaction_path, identity_path)})
        d144_identity = read_small_json(identity_path)
        release = transaction.get("release_identity")
        installed_app = installed_app_inventory(app)
        installed_venv = installed_app_inventory(venv)
        candidate_inventory = transaction.get("candidate")
        recorded_app = (candidate_inventory.get("app")
                        if isinstance(candidate_inventory, dict) else None)
        recorded_venv = (candidate_inventory.get("venv")
                         if isinstance(candidate_inventory, dict) else None)
        extra_app_paths = (set(installed_app) - set(recorded_app)
                           if isinstance(recorded_app, dict) else set())
        source_files_match = (
            isinstance(recorded_app, dict)
            and all(installed_app.get(name) == metadata
                    for name, metadata in recorded_app.items())
            and all(
                "__pycache__" in Path(name).parts
                and (name.endswith(".pyc") or Path(name).name == "__pycache__")
                for name in extra_app_paths
            )
        )
        if (transaction.get("schema") != "D144_STATE_PRESERVING_V1"
                or transaction.get("phase") != "COMMITTED"
                or transaction.get("slot", slot) != slot
                or type(transaction.get("transaction")) is not str
                or d144_identity.get("schema") != "D144_RELEASE_IDENTITY_V1"
                or type(d144_identity.get("source_sha")) is not str
                or len(d144_identity["source_sha"]) != 40
                or any(c not in "0123456789abcdef" for c in d144_identity["source_sha"])
                or type(d144_identity.get("candidate_identity_sha256")) is not str
                or len(d144_identity["candidate_identity_sha256"]) != 64
                or any(c not in "0123456789abcdef" for c in d144_identity["candidate_identity_sha256"])
                or d144_identity.get("transaction") != transaction.get("transaction")
                or release != {k: d144_identity[k] for k in
                               ("schema", "source_sha", "candidate_identity_sha256")}
                or not source_files_match
                or recorded_venv != installed_venv):
            raise ValueError("D144 installed release identity does not match committed app/venv")
    retirement = quarantine.get("retirement")
    preserved_guard = None
    preserved_quarantine = None
    if not session_present and quarantine.get("quarantined") is True:
        # A Python-only release may need to preserve an orphaned active
        # quarantine while charge_session.json is absent. This is identity
        # capture only: it does not clear the journal or authorize charging.
        identity = quarantine.get("identity")
        reason = quarantine.get("reason")
        incident_id = quarantine.get("incident_id")
        incident_utc = quarantine.get("incident_utc")
        valid_reason = (
            isinstance(reason, str) and reason.startswith((
                "main_guard_current_setpoint_transaction_unconfirmed:",
                "main_guard_current_ocp_transaction_unconfirmed:",
            ))
        )
        try:
            from datetime import datetime
            from uuid import UUID
            if not isinstance(incident_id, str):
                raise ValueError("incident ID missing")
            UUID(incident_id)
            if not isinstance(incident_utc, str):
                raise ValueError("incident timestamp missing")
            datetime.fromisoformat(incident_utc.replace("Z", "+00:00"))
            valid_time = True
        except (TypeError, ValueError, OverflowError):
            valid_time = False
        if (
            set(quarantine) != {
                "owner", "schema_version", "quarantined", "reason",
                "incident_id", "incident_utc", "identity",
            }
            or quarantine.get("owner") != "runtime.charge.recovery_quarantine_journal"
            or quarantine.get("schema_version") != 1
            or not valid_reason
            or not valid_time
            or not isinstance(identity, dict)
            or set(identity) != {"session_id", "battery_id"}
            or any(type(identity.get(key)) is not str or not identity[key].strip()
                   for key in ("session_id", "battery_id"))
        ):
            raise ValueError("active orphan quarantine identity is not authentic")
        preserved_quarantine = {
            "incident_id": incident_id,
            "incident_utc": incident_utc,
            "reason": reason,
            "session_id": identity["session_id"],
            "battery_id": identity["battery_id"],
            "session_absent": True,
            "quarantine_sha256": before[str(quarantine_path)],
        }
    elif session_present and session.get("stage") in {
        "Main Charge", "Mix Mode", "Безопасное ожидание",
    }:
        # Preserve MAIN's sealed Guard in MIX and final SAFE_WAIT, including
        # the interrupted Storage transition. These are saved identities,
        # never authority to resume Output after a service restart.
        history = session.get("stage_history") or []
        main_to_mix = any(
            isinstance(step, dict) and step.get("from") == "Main Charge"
            and step.get("to") == "Mix Mode" for step in history
        )
        if session["stage"] in {"Mix Mode", "Безопасное ожидание"} and not main_to_mix:
            raise ValueError("guarded session lacks historical MAIN transition")
        if session["stage"] == "Безопасное ожидание":
            try:
                from tools.d137_guarded_final_safe_wait import valid_guarded_final_wait
            except ModuleNotFoundError:
                from d137_guarded_final_safe_wait import valid_guarded_final_wait
            if not valid_guarded_final_wait(session):
                raise ValueError("guarded final SAFE_WAIT continuation invalid")
        # Independent D091 Native/HA proof confirms Output OFF; bind every
        # persisted byte and validate the canonical guard snapshot.
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
        guard_record = session[GUARD_KEY]
        # read_guard intentionally resets the restored in-memory observation
        # to False because restart breaks continuity. Preserve and inspect the
        # sealed historical snapshot separately; never rewrite it here.
        persisted_last_output_on = guard_record["snapshot"].get("last_output_on")
        reconciliation_fields = {
            "schema", "captured_at_epoch", "service_main_pid", "native_sensor_state_fresh",
            "ha102_output_off", "ha102_current_a", "esp128_output_off",
            "esp128_current_a", "edge_lease_armed", "edge_boot_quarantine",
            "physical_node_owner_count", "active_session", "source_nonces",
        }
        reconciliation_valid = False
        if isinstance(physical_off_reconciliation, dict):
            try:
                captured = physical_off_reconciliation["captured_at_epoch"]
                nonces = physical_off_reconciliation["source_nonces"]
                def zero_reading(key):
                    value = physical_off_reconciliation.get(key)
                    return (type(value) in (int, float) and math.isfinite(value)
                            and abs(value) <= .05)
                reconciliation_valid = (
                    set(physical_off_reconciliation) == reconciliation_fields
                    and physical_off_reconciliation.get("schema") == "D142_VALIDATED_D091_OFF_V1"
                    and type(captured) in (int, float) and math.isfinite(captured)
                    and 0 <= time.time() - captured <= 8.0
                    and type(physical_off_reconciliation.get("service_main_pid")) is int
                    and physical_off_reconciliation.get("service_main_pid") == pid
                    and physical_off_reconciliation.get("native_sensor_state_fresh") is True
                    and physical_off_reconciliation.get("ha102_output_off") is True
                    and physical_off_reconciliation.get("esp128_output_off") is True
                    and all(zero_reading(key) for key in (
                        "ha102_current_a", "esp128_current_a"))
                    and physical_off_reconciliation.get("edge_lease_armed") is False
                    and physical_off_reconciliation.get("edge_boot_quarantine") is False
                    and type(physical_off_reconciliation.get("physical_node_owner_count")) is int
                    and physical_off_reconciliation.get("physical_node_owner_count") == 1
                    and physical_off_reconciliation.get("active_session") is True
                    and type(nonces) is list and len(nonces) == 2
                    and all(type(n) is str and n for n in nonces) and nonces[0] != nonces[1]
                )
            except (KeyError, TypeError, ValueError, OverflowError):
                reconciliation_valid = False
        reconciled_historical_on = persisted_last_output_on is True and reconciliation_valid
        if (revision <= 0 or guard.pending is not None or guard.fault is not None
                or (persisted_last_output_on is not False and not reconciled_historical_on)
                or guard.last_stage_main is not True
                or abs(guard.capacity_ah - float(session["ah_limit"])) > 1e-6):
            raise ValueError("active MAIN guard is pending, faulted, or not state-preserving OFF")
        preserved_guard = {"session_id": guard.session_id,
                           "battery_id": guard.battery_id,
                           "revision": revision,
                           "last_output_on": persisted_last_output_on,
                           "guard_sha256": guard_record["sha256"],
                           "guard_snapshot_sha256": hashlib.sha256(json.dumps(
                               guard_record["snapshot"], sort_keys=True,
                               separators=(",", ":"), ensure_ascii=True,
                               allow_nan=False).encode("ascii")).hexdigest()}
    elif not isinstance(retirement, dict) or quarantine.get("quarantined") is not False:
        raise ValueError("durable retirement and verified-OFF identity do not agree")
    elif session_present:
        # An operator may retire a later, unrelated AUTO session after the
        # historical recovery-quarantine incident was already retired.
        # The current atomic tombstone, not the old incident, is the identity
        # that must be preserved by a software update.
        independent_off = (
            session.get("owner") == "runtime.charge.persistence"
            and session.get("schema_version") == 1
            and session.get("retirement_kind") == "operator_recovery_clearance"
            and session.get("output_intent") == "verified_off"
            and isinstance(session.get("session_id"), str) and bool(session["session_id"])
            and isinstance(session.get("battery_id"), str) and bool(session["battery_id"])
            and isinstance(session.get("retired_utc"), str) and bool(session["retired_utc"])
            and isinstance(session.get("verified_off_recorded_utc"), str)
            and bool(session["verified_off_recorded_utc"])
            and isinstance(session.get("verified_off_transaction_id"), str)
            and session["verified_off_transaction_id"].startswith("native-ha-independent-off:")
            and len(session["verified_off_transaction_id"].split(":")[-1]) == 64
        )
        historical_matching = (
            retirement.get("session_id") == session.get("session_id")
            and retirement.get("confirmed_off_evidence") == session.get("verified_off_transaction_id")
        )
        if (session.get("state") != "retired" or session.get("stage") != "RETIRED"
                or not (historical_matching or independent_off)):
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
            "marker_sha256": before[str(marker)] if marker_present else None,
            "installed_release": d144_identity,
            "candidate_inventory_present": False
        },
        "retired_session": (None if preserved_guard or preserved_quarantine else {
            "session_id": session.get("session_id") if session_present else retirement["session_id"],
            "off_evidence": (session.get("verified_off_transaction_id")
                             if session_present else retirement["confirmed_off_evidence"]),
            "session_sha256": before[str(session_path)] if session_present else None,
            "session_absent": not session_present,
            "quarantine_sha256": before[str(quarantine_path)]
        }),
        "preserved_quarantine": preserved_quarantine,
        "preserved_guarded_main": ({
            **preserved_guard,
            "session_sha256": before[str(session_path)],
            "quarantine_sha256": before[str(quarantine_path)],
            "physical_off_reconciliation": physical_off_reconciliation,
            "automatic_resume_authorized": False,
        } if preserved_guard else None)
    }
    # The identity digest pins durable app/session/guard bytes. A fresh D091
    # proof gates admission, but its timestamp and independent source nonces
    # are observation evidence rather than durable preimage identity. Keep the
    # validated proof in the returned record while excluding only that transient
    # subrecord from the stable candidate identity.
    identity_payload = payload
    if preserved_guard is not None:
        identity_payload = json.loads(json.dumps(payload, sort_keys=True,
                                                  separators=(",", ":"), ensure_ascii=True))
        identity_payload["preserved_guarded_main"].pop("physical_off_reconciliation")
    canonical = json.dumps(identity_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
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
