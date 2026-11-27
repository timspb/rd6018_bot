"""Read-only production admission through the canonical D090 transaction owner.

D144's engine remains deliberately disconnected from production service lifecycle.
This operation acquires the SAME lock that owns D090, runs the reviewed D142
combined proof, and returns evidence, never authorization to start a cutover.
"""
from __future__ import annotations

from pathlib import Path

import node104_d090_transaction as d090
from tools.d142_readonly_prestop import assess


def _service_account():
    import grp
    import pwd

    return pwd.getpwnam("rd6018"), grp.getgrnam("rd6018")


def _validate_service_readable_tree(path: Path, *, uid: int, gid: int) -> None:
    """Fail closed unless rd6018 can traverse directories and read files.

    Ownership may remain root:rd6018, but group access must be present. This
    deliberately checks every entry before D144 can stop the running service.
    """
    if path.is_symlink() or not path.is_dir():
        raise d090.TransactionError("D145 candidate tree root is unsafe")
    for item in (path, *path.rglob("*")):
        info = item.lstat()
        if item.is_symlink():
            continue
        if info.st_uid not in (0, uid) or info.st_gid not in (gid,):
            raise d090.TransactionError("D145 candidate ownership is outside root:rd6018 policy")
        mode = info.st_mode & 0o777
        required = 0o050 if item.is_dir() else 0o040 | ((mode & 0o0100) >> 3)
        if mode & required != required:
            raise d090.TransactionError("D145 candidate is not traversable/readable by rd6018")


def _prepare_service_readable_tree(path: Path, *, gid: int) -> None:
    """Apply root:rd6018 ownership and least-privilege group read access."""
    import os
    if path.is_symlink() or not path.is_dir():
        raise d090.TransactionError("D145 candidate tree root is unsafe")
    for item in (path, *path.rglob("*")):
        info = item.lstat()
        if item.is_symlink():
            continue
        mode = info.st_mode & 0o777
        if item.is_dir():
            mode = (mode & 0o707) | 0o050
        else:
            mode = (mode & 0o707) | 0o040 | ((mode & 0o0100) >> 3)
        os.chown(item, 0, gid)
        os.chmod(item, mode)


def prepare_only(owner: d090.D090Transaction, *, stage: Path,
                 source_sha: str, preimage_sha256: str,
                 collector: Path) -> dict:
    if (owner.offline or owner.root != Path(d090.release.ROOT)
            or owner.host_check is not d090.production_host_check
            or not owner.software_release
            or not isinstance(owner.service, d090.SystemdService)):
        raise d090.TransactionError("D144 production owner binding invalid")
    if source_sha != owner.pinned.source_sha:
        raise d090.TransactionError("D144 candidate source differs from owner pin")
    with owner._locked():
        owner.host_check()
        owner.release_admission()
        if not owner.service.layout_valid() or not owner.service.active():
            raise d090.TransactionError("D144 production layout or service is not healthy")
        pid = owner.service.main_pid()
        if pid <= 0:
            raise d090.TransactionError("D144 invalid service MainPID")
        result = assess(owner.root, stage, pid=pid, source_sha=source_sha,
                        preimage_sha256=None, collector=collector,
                        validate_app_inventory=lambda preimage: d090.verify_pinned_preimage_app(
                            owner.root / "app", preimage["app_inventory_sha256"]))
        if result.get("preflight") != "PASS_AT_OBSERVATION_ONLY":
            raise d090.TransactionError("D142 pre-stop checks did not pass")
        return {
            "schema": "D144_OWNER_PREPARE_ONLY_V1",
            "status": "PREPARE_ONLY_PASS",
            "service_pid": pid,
            "candidate_identity_sha256": result["candidate_identity_sha256"],
            "observed_preimage_sha256": result["observed_preimage_sha256"],
            "fresh_d091_off": result["fresh_d091_off"],
            "capacity_pass": result["capacity_pass"],
            "preserved_guarded_main": bool(result.get("preserved_guarded_main")),
            "preserved_guard": result.get("preserved_guard"),
            "preserved_quarantine": result.get("preserved_quarantine"),
            "activation_authorized": False,
        }


def execute_under_owner(owner: d090.D090Transaction, *, stage: Path,
                        preimage_sha256: str, collector: Path,
                        failpoint=None) -> dict:
    """Single-owner production transaction core; no standalone entrypoint.

    Acquire canonical D090 lock first and keep it through staging, fresh OFF
    evidence, service stop, candidate start, and durable D144 COMMITTED.
    Does not revive or modify the historical D090 transaction.
    """
    if (owner.offline or owner.root != Path(d090.release.ROOT)
            or owner.host_check is not d090.production_host_check
            or not owner.software_release
            or not isinstance(owner.service, d090.SystemdService)):
        raise d090.TransactionError("D145 production owner binding invalid")
    from tools.d140_disk_guard import require_capacity
    from tools.d144_state_preserving_transition import OwnerTransition, transaction_slot
    from tools.d149_observer_router import ReadOnlyObserverRouter
    import shutil

    with owner._locked():
        # This checks exact D137/D138 bytes, minimum rollback capacity, and
        # NEW D091 Native/HA observations while the original service runs.
        prepared = prepare_only(
            owner, stage=stage, source_sha=owner.pinned.source_sha,
            preimage_sha256=preimage_sha256, collector=collector)
        if prepared.get("status") != "PREPARE_ONLY_PASS":
            raise d090.TransactionError("D145 prepare-only gate failed")
        slot = transaction_slot(owner.root)
        candidate = owner.root / ("candidate-d144" if slot == 1 else "candidate-d144-" + str(slot))
        if candidate.exists() or candidate.is_symlink():
            raise d090.TransactionError("D145 candidate path already occupied")
        candidate.mkdir(mode=0o700)
        staged = {"app": d090.inventory(stage / "tree"),
                  "venv": d090.inventory(stage / "venv")}
        shutil.copytree(stage / "tree", candidate / "app", symlinks=True)
        shutil.copytree(stage / "venv", candidate / "venv", symlinks=True)
        try:
            service_user, service_group = _service_account()
        except KeyError as exc:
            raise d090.TransactionError("D145 rd6018 service account is absent") from exc
        for name in ("app", "venv"):
            _prepare_service_readable_tree(candidate / name,
                                           gid=service_group.gr_gid)
            _validate_service_readable_tree(candidate / name,
                                            uid=service_user.pw_uid,
                                            gid=service_group.gr_gid)
        d090._durable_tree(candidate)
        wanted = {name: d090.inventory(candidate / name)
                  for name in ("app", "venv")}
        for name in ("app", "venv"):
            if set(wanted[name]) != set(staged[name]):
                raise d090.TransactionError("D145 copied candidate inventory mismatch")
            for relative, expected in staged[name].items():
                actual = wanted[name][relative]
                if "link" in expected:
                    matches = actual == expected
                elif "directory" in expected:
                    matches = actual.get("directory") is True
                else:
                    matches = all(actual.get(key) == expected.get(key)
                                  for key in ("sha256", "size"))
                if not matches:
                    raise d090.TransactionError("D145 copied candidate content mismatch")
        if any(not (candidate / name).is_dir() for name in ("app", "venv")):
            raise d090.TransactionError("D145 copied candidate inventory mismatch")
        # Disk is remeasured AFTER copying the staged release, not from an
        # optimistic check made before consuming additional space.
        require_capacity(owner.root, candidate)
        before = {name: d090.inventory(owner.root / name)
                  for name in ("app", "venv")}
        identity = {
            "schema": "D144_RELEASE_IDENTITY_V1",
            "source_sha": owner.pinned.source_sha,
            "candidate_identity_sha256": prepared["candidate_identity_sha256"],
        }
        # Every D145 operation is a state-preserving Python-only release.
        # Use the pinned D151 collector even when charge_session.json is absent:
        # an active quarantine journal is also state that must survive the swap.
        router = ReadOnlyObserverRouter(
            owner.root, state_preserving_recovery=True)
        previous_proof = owner.proof
        proof_index = [0]
        phases = ("PRE_STOP", "PRE_STOP", "STOPPED", "POST_START")
        def fresh_proof(*, require_stopped: bool):
            # Exactly two pre-stop reads, one stopped-service proof, and one
            # restarted-service proof. Never substitute another phase.
            index = proof_index[0]
            if index >= len(phases):
                raise d090.TransactionError("unexpected D149 proof count")
            phase = phases[index]
            if bool(require_stopped) != (phase == "STOPPED"):
                raise d090.TransactionError("D149 physical proof phase mismatch")
            router.select(phase)
            owner.proof = router
            # ALL D145 releases are Python-only and use D151's independent
            # HA/Native Output-OFF and zero-current proof. Battery voltage
            # may remain nonzero with R18 OFF even without active quarantine.
            # The legacy hardware/firmware release still uses _read_proof.
            result = owner._read_recovery_proof(
                require_service_stopped=require_stopped)
            proof_index[0] += 1
            return result
        transition = OwnerTransition(
            owner.root, owner.service, candidate=candidate,
            evidence=fresh_proof, expected_before=before,
            expected_candidate=wanted,
            legacy_journal_sha256=d090.digest(owner.journal),
            candidate_stable=lambda: owner.service.stable(owner.pinned.source_sha),
            restored_stable=lambda: owner.service.stable(owner.pinned.old_source_sha),
            release_identity=identity, failpoint=failpoint, slot=slot)
        try:
            result = transition.run()
            if proof_index[0] != len(phases):
                raise d090.TransactionError("D149 proof sequence incomplete")
            return result
        finally:
            owner.proof = previous_proof


def _restored_quarantine_contained(owner: d090.D090Transaction, *,
                                   evidence) -> bool:
    """D144 RESTORED means original bytes are safely back, not charge readiness.

    Only the interrupted, exact D084 START_PENDING/active journal with a fresh
    independent D151 OFF proof may be classified as safely restored. This
    method cannot authorize a release, managed START, or Output ON.
    """
    import json
    import math
    import subprocess
    import time
    from runtime.charge.persistence import SESSION_FILE, read_start_pending
    from runtime.journal.recovery_quarantine import RecoveryQuarantineJournal
    # Preserve the D090 owner's exact PhysicalOffProof class identity; importing
    # the sibling module under a second package name creates an incompatible type.
    validate_physical_off = d090.release.validate_physical_off
    service = owner.service
    if not service.active():
        return False
    pid = service.main_pid()
    if pid <= 0 or service._run(
        "systemctl", "show", d090.release.SERVICE,
        "-p", "NRestarts", "--value",
    ) != "0":
        return False
    process_argv = Path("/proc").joinpath(str(pid), "cmdline").read_bytes().split(b"\0")
    expected_app = str(owner.root / "app/bot.py").encode()
    if expected_app not in process_argv:
        return False
    others = []
    for directory in Path("/proc").iterdir():
        if not directory.name.isdigit():
            continue
        try:
            if expected_app in directory.joinpath("cmdline").read_bytes().split(b"\0"):
                others.append(int(directory.name))
        except OSError:
            continue
    if others != [pid]:
        return False
    # The D144 state-preserving releases intentionally do not require the
    # historical .deploy_sha marker. The canonical identity is instead the
    # latest exact COMMITTED D144 installed-release receipt and its matching
    # transaction, corroborated by the restored byte inventory in recover().
    marker = owner.root / ".deploy_sha"
    if marker.is_symlink() or (marker.exists() and (
            not marker.is_file()
            or marker.read_text().strip() != owner.pinned.old_source_sha)):
        return False
    receipts = list(owner.root.glob("D144_INSTALLED_RELEASE_*.json"))
    try:
        releases = sorted((int(x.stem.rsplit("_", 1)[-1]), x)
                           for x in receipts if x.stem.rsplit("_", 1)[-1].isdigit())
    except (OSError, ValueError):
        return False
    if not releases or len(releases) != len(receipts):
        return False
    slot, release_path = releases[-1]
    transaction_path = owner.root / f"D144_TRANSACTION_{slot}.json"
    if (release_path.is_symlink() or transaction_path.is_symlink()
            or not transaction_path.is_file()):
        return False
    try:
        release_id = json.loads(release_path.read_text())
        committed = json.loads(transaction_path.read_text())
    except (OSError, ValueError):
        return False
    if (release_id.get("source_sha") != owner.pinned.old_source_sha
            or committed.get("phase") != "COMMITTED"
            or committed.get("slot") != slot
            or committed.get("transaction") != release_id.get("transaction")
            or committed.get("release_identity", {}).get("source_sha")
            != owner.pinned.old_source_sha):
        return False
    state = owner.root / "state"
    session = state / "charge_session.json"
    if session.is_symlink():
        return False
    raw, pending, error = read_start_pending(session)
    if error or pending is None or pending.get("previous_exists") is not False:
        return False
    candidate = pending.get("candidate")
    if type(candidate) is not dict:
        return False
    journal = RecoveryQuarantineJournal(state / "session_recovery_quarantine.json")
    try:
        incident = journal.incident_binding()
    except Exception:
        return False
    if (incident.get("reason") != "start_enable_off_receipt_invalid"
            or incident.get("session_id") != candidate.get("v2_trace_session_id")
            or incident.get("battery_id") != candidate.get("v2_battery_id")):
        return False
    # The pre-existing D151 runner is the sole observer for the current
    # generation. It reports ESP Native and HA independently and includes
    # the running service PID, active session and lease state.
    proof = evidence(require_stopped=False)
    validate_physical_off(proof, now=time.time(),
                          require_service_stopped=False,
                          allow_active_session=True, software_release=True)
    if proof.service_main_pid != pid or proof.active_session is not True:
        return False
    # The old B1056 process intentionally has no Telegram ready marker while
    # durable START_PENDING blocks startup. This is a contained restoration,
    # never an operational release or a health claim.
    started = service._run("systemctl", "show", d090.release.SERVICE,
                           "-p", "ActiveEnterTimestamp", "--value")
    if not started or started == "n/a":
        return False
    logs = service._run("journalctl", "-u", d090.release.SERVICE,
                        "--since", started, "--no-pager", "-o", "cat")
    if any(word in logs for word in (
            "Traceback (most recent call last)", "Unauthorized", "database is locked",
            "Start polling", "Run polling for bot")):
        return False
    return "START_PENDING recovery quarantined" in logs


def recover_under_owner(owner: d090.D090Transaction, *,
                        expected_candidate_identity_sha256: str) -> dict:
    """Recover an interrupted D144 ledger under canonical D090 lock.

    Recovery does not require D142's preimage (which may already have been
    replaced) and never invokes the original historical D090 recover().
    """
    if (owner.offline or owner.root != Path(d090.release.ROOT)
            or owner.host_check is not d090.production_host_check
            or not owner.software_release
            or not isinstance(owner.service, d090.SystemdService)):
        raise d090.TransactionError("D145 recovery owner binding invalid")
    from tools.d144_state_preserving_transition import OwnerTransition, JOURNAL
    import json
    from tools.d149_observer_router import ReadOnlyObserverRouter
    with owner._locked():
        owner.host_check()
        matches = []
        for candidate_path in owner.root.glob("D144_TRANSACTION*.json"):
            if candidate_path.is_symlink() or not candidate_path.is_file():
                raise d090.TransactionError("D145 unsafe D144 history entry")
            try:
                candidate_record = json.loads(candidate_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                raise d090.TransactionError("D145 unreadable D144 history entry")
            candidate_identity = candidate_record.get("release_identity", {})
            if (candidate_identity.get("source_sha") == owner.pinned.source_sha
                    and candidate_identity.get("candidate_identity_sha256") == expected_candidate_identity_sha256
                    and candidate_record.get("phase") not in ("COMMITTED", "RESTORED")):
                matches.append((candidate_path, candidate_record))
        if len(matches) != 1:
            raise d090.TransactionError("D145 interrupted D144 transaction identity missing or ambiguous")
        path, record = matches[0]
        if path.name == JOURNAL:
            slot = 1
        else:
            slot = int(path.name.removeprefix("D144_TRANSACTION_").removesuffix(".json"))
        identity = record.get("release_identity")
        if (record.get("schema") != "D144_STATE_PRESERVING_V1"
                or not isinstance(identity, dict)
                or identity.get("schema") != "D144_RELEASE_IDENTITY_V1"
                or identity.get("source_sha") != owner.pinned.source_sha
                or identity.get("candidate_identity_sha256") != expected_candidate_identity_sha256):
            raise d090.TransactionError("D145 candidate identity changed")
        before = record.get("before")
        candidate_manifest = record.get("candidate")
        if not isinstance(before, dict) or not isinstance(candidate_manifest, dict):
            raise d090.TransactionError("D145 backup/candidate manifest missing")
        # Recovery has independent fresh Native/HA proof and DOES NOT
        # roll back any data in state/. Old D090 remains historical.
        router = ReadOnlyObserverRouter(owner.root)
        router.select("RECOVERY")
        previous_proof = owner.proof
        def fresh_recovery_proof(*, require_stopped: bool):
            owner.proof = router
            return owner._read_recovery_proof(require_service_stopped=require_stopped)
        transition = OwnerTransition(
            owner.root, owner.service,
            candidate=owner.root / ("candidate-d144" if slot == 1 else "candidate-d144-" + str(slot)),
            evidence=fresh_recovery_proof, expected_before=before,
            expected_candidate=candidate_manifest,
            legacy_journal_sha256=d090.digest(owner.journal),
            candidate_stable=lambda: owner.service.stable(owner.pinned.source_sha),
            restored_stable=lambda: (
                owner.service.stable(owner.pinned.old_source_sha)
                or _restored_quarantine_contained(owner, evidence=fresh_recovery_proof)
            ),
            release_identity=identity, slot=slot)
        try:
            return transition.recover()
        finally:
            owner.proof = previous_proof
