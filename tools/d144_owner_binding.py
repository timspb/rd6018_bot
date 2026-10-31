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
        def fresh_proof(*, require_stopped: bool):
            # Every invocation creates new Native/HA readings and validates
            # distinct source nonces in the canonical D090 transaction owner.
            return owner._read_proof(require_service_stopped=require_stopped)
        transition = OwnerTransition(
            owner.root, owner.service, candidate=candidate,
            evidence=fresh_proof, expected_before=before,
            expected_candidate=wanted,
            legacy_journal_sha256=d090.digest(owner.journal),
            candidate_stable=lambda: owner.service._stable_process(owner.pinned.source_sha),
            restored_stable=lambda: owner.service._stable_process(owner.pinned.old_source_sha),
            release_identity=identity, failpoint=failpoint)
        return transition.run()
