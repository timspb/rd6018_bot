"""Read-only production admission through the canonical D090 transaction owner.

D144's engine remains deliberately disconnected from production service lifecycle.
This operation acquires the SAME lock that owns D090, runs the reviewed D142
combined proof, and returns evidence, never authorization to start a cutover.
"""
from __future__ import annotations

from pathlib import Path

import node104_d090_transaction as d090
from tools.d142_readonly_prestop import assess


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
                        preimage_sha256=preimage_sha256, collector=collector)
        if result.get("preflight") != "PASS_AT_OBSERVATION_ONLY":
            raise d090.TransactionError("D142 pre-stop checks did not pass")
        return {
            "schema": "D144_OWNER_PREPARE_ONLY_V1",
            "status": "PREPARE_ONLY_PASS",
            "service_pid": pid,
            "candidate_identity_sha256": result["candidate_identity_sha256"],
            "observed_preimage_sha256": preimage_sha256,
            "fresh_d091_off": result["fresh_d091_off"],
            "capacity_pass": result["capacity_pass"],
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
    from tools.d144_state_preserving_transition import OwnerTransition
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
        candidate = owner.root / "candidate-d144"
        if candidate.exists() or candidate.is_symlink():
            raise d090.TransactionError("D145 candidate path already occupied")
        candidate.mkdir(mode=0o700)
        shutil.copytree(stage / "tree", candidate / "app", symlinks=True)
        shutil.copytree(stage / "venv", candidate / "venv", symlinks=True)
        d090._durable_tree(candidate)
        wanted = {"app": d090.inventory(stage / "tree"),
                  "venv": d090.inventory(stage / "venv")}
        if any(d090.inventory(candidate / name) != wanted[name]
               for name in ("app", "venv")):
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
        router = ReadOnlyObserverRouter(owner.root)
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
            result = owner._read_proof(require_service_stopped=require_stopped)
            proof_index[0] += 1
            return result
        transition = OwnerTransition(
            owner.root, owner.service, candidate=candidate,
            evidence=fresh_proof, expected_before=before,
            expected_candidate=wanted,
            legacy_journal_sha256=d090.digest(owner.journal),
            candidate_stable=lambda: owner.service._stable_process(owner.pinned.source_sha),
            restored_stable=lambda: owner.service._stable_process(owner.pinned.old_source_sha),
            release_identity=identity, failpoint=failpoint)
        try:
            result = transition.run()
            if proof_index[0] != len(phases):
                raise d090.TransactionError("D149 proof sequence incomplete")
            return result
        finally:
            owner.proof = previous_proof


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
        path = owner.root / JOURNAL
        if path.is_symlink() or not path.is_file():
            raise d090.TransactionError("D145 durable recovery journal missing")
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError) as e:
            raise d090.TransactionError("D145 durable recovery journal invalid") from e
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
            owner.root, owner.service, candidate=owner.root / "candidate-d144",
            evidence=fresh_recovery_proof, expected_before=before,
            expected_candidate=candidate_manifest,
            legacy_journal_sha256=d090.digest(owner.journal),
            candidate_stable=lambda: owner.service._stable_process(owner.pinned.source_sha),
            restored_stable=lambda: owner.service._stable_process(owner.pinned.old_source_sha),
            release_identity=identity)
        try:
            return transition.recover()
        finally:
            owner.proof = previous_proof
