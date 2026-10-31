#!/usr/bin/env python3
"""D145/D146 narrow node104 entrypoint, bound to the canonical D090 owner.

The entrypoint never calls the historical D090 activate/recover methods. It
loads one exact D146 profile and routes prepare/execute/recovery through the
owner-locked D145 integration. Execution and recovery are node-local actions;
the host identity check runs before either can reach transaction code.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

# D090's established modules use top-level sibling imports when run as scripts.
_TOOLS_DIR = str(Path(__file__).resolve().parent)
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

try:
    import node104_d090_release as release
    import node104_d090_transaction as d090
    from node104_d124_release_profile import load_software_release_profile
    from d144_owner_binding import execute_under_owner, prepare_only, recover_under_owner
    from d149_observer_router import D147_SHA, D148_SHA, ReadOnlyObserverRouter
except ModuleNotFoundError:
    from tools import node104_d090_release as release
    from tools import node104_d090_transaction as d090
    from tools.node104_d124_release_profile import load_software_release_profile
    from tools.d144_owner_binding import execute_under_owner, prepare_only, recover_under_owner
    from tools.d149_observer_router import D147_SHA, D148_SHA, ReadOnlyObserverRouter


PROFILE_SHA256 = "a2610e4c26c6d2ff6fcd9ac3bc12a1e92aaf0f9d1c49059dcfe5bc2462934e47"
SOURCE_SHA = "d351c208cbf8666f881a4660df6a0b211170e857"
PREIMAGE_INVENTORY_SHA256 = "9651e979e6394fd53ee373010f845ba00e7ccbbfa85a7a313b95893a0edea444"
CANDIDATE_IDENTITY_SHA256 = "45b6ae0e2dc2f42ee76eaca8311178fd76f92e0254b63e60f3d7393ceee1979e"
DEFAULT_STAGE = Path("/tmp/d138_stage_d351c208")


def default_profile() -> Path:
    return Path(__file__).resolve().parents[1] / "docs/operations/evidence/D146_D138_NODE104_PROFILE.json"


def _profile_digest(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise d090.TransactionError("D146 profile must be a regular non-symlink file")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_pinned_profile(path: Path):
    """Read and validate the exact reviewed D146 profile without side effects."""
    if _profile_digest(path) != PROFILE_SHA256:
        raise d090.TransactionError("D146 profile digest differs from entrypoint pin")
    try:
        pinned, preimage_sha, record = load_software_release_profile(path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise d090.TransactionError("D146 profile failed schema/admission validation") from exc
    if (pinned.source_sha != SOURCE_SHA
            or preimage_sha != PREIMAGE_INVENTORY_SHA256
            or record.get("proof_collector_sha256") != D147_SHA
            or pinned.node != "node104" or pinned.firmware != "2.3-ha-canonical"
            or pinned.edge_lease_ttl_s != 900 or pinned.edge_renewal_s != 300):
        raise d090.TransactionError("D146 source, preimage, observer, or edge pin mismatch")
    return pinned, preimage_sha, record


def build_owner(profile_path: Path):
    """Construct a software-release D090 owner without invoking its CLI phases."""
    pinned, preimage_sha, _record = load_pinned_profile(profile_path)

    def admission() -> None:
        # Re-read on every owner admission to close profile replacement races.
        current_pin, current_preimage, _ = load_pinned_profile(profile_path)
        if current_pin != pinned or current_preimage != preimage_sha:
            raise d090.TransactionError("D146 profile changed during owner lifetime")

    router = ReadOnlyObserverRouter(Path(release.ROOT))
    return d090.D090Transaction(
        Path(release.ROOT), service=d090.SystemdService(pinned), proof=router,
        host_check=d090.production_host_check, acceptance=lambda: None,
        venv_builder=d090.production_venv_builder, pinned=pinned,
        software_release=True, preimage_inventory_sha256=preimage_sha,
        release_admission=admission,
    )


def verify_pinned_observer(root: Path, relative_path: str, expected_sha256: str) -> Path:
    """Fail closed unless a frozen observer is present before a phase starts."""
    path = root / relative_path
    parent = path.parent
    if (parent.is_symlink() or not parent.is_dir()
            or parent.stat().st_mode & 0o022
            or path.is_symlink() or not path.is_file()
            or path.stat().st_mode & 0o222
            or _profile_digest(path) != expected_sha256):
        raise d090.TransactionError("pinned D147/D148 observer missing or changed")
    return path


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("prepare", "execute", "recover"))
    parser.add_argument("--profile", type=Path, default=default_profile())
    parser.add_argument("--stage", type=Path, default=DEFAULT_STAGE)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = make_parser().parse_args(argv)
    d090.production_host_check()
    owner = build_owner(args.profile)
    root = Path(release.ROOT)
    observer = verify_pinned_observer(
        root, "d147-proof/node104_d091_physical_proof_collector.py", D147_SHA)

    if args.phase == "prepare":
        result = prepare_only(
            owner, stage=args.stage, source_sha=SOURCE_SHA,
            preimage_sha256=PREIMAGE_INVENTORY_SHA256, collector=observer)
    elif args.phase == "execute":
        verify_pinned_observer(
            root, "d147-proof/d148_recovery_d091_collector.py", D148_SHA)
        result = execute_under_owner(
            owner, stage=args.stage, preimage_sha256=PREIMAGE_INVENTORY_SHA256,
            collector=observer)
    else:
        verify_pinned_observer(
            root, "d147-proof/d148_recovery_d091_collector.py", D148_SHA)
        result = recover_under_owner(
            owner, expected_candidate_identity_sha256=CANDIDATE_IDENTITY_SHA256)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())