"""Detached service stop hook: independently request and prove physical OFF."""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

from .bounded import run_bounded

OPT_IN = "YES_I_HAVE_REVIEWED_BENCH_GATES"
CONFIG_ROOT = "/opt/services/rd6018-bot/app/config"


def _require_identity(run_id: str, source: str) -> None:
    # This path runs after supervisor/child failure, including absent or
    # untrusted job manifests. Identity gates the pinned hardware connection,
    # but never suppresses an emergency OFF attempt on an untrusted manifest.
    if source != "node104-deployed" or not run_id or len(run_id) > 128:
        raise RuntimeError("explicit D061 stop source and run identity required")
    try:
        from .transient import require_node104
        require_node104()
    except Exception as exc:
        raise RuntimeError("D061 stop helper requires root on exact node104") from exc
    expected_run = os.environ.get("D061_ACCEPTANCE_RUN_ID", "")
    if expected_run and expected_run != run_id:
        raise RuntimeError("D061 stop run identity does not match service instance")


def _run_adapter() -> object:
    from .hardware_off import emergency_off
    return asyncio.run(emergency_off(config_root=CONFIG_ROOT, timeout_s=10.0))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--enable", action="store_true")
    parser.add_argument("--source", default="")
    parser.add_argument("--run-id", default="")
    args, _unknown = parser.parse_known_args(argv)
    if not args.enable or os.environ.get("D061_OFF_ADAPTER_OPT_IN") != OPT_IN:
        print("D061 emergency OFF denied: explicit stop-hook opt-in is missing", file=sys.stderr)
        return 78
    try:
        _require_identity(args.run_id, args.source)
        proof = run_bounded(_run_adapter, 12.0)
        if not (getattr(proof, "ha_off", False) and getattr(proof, "native_off", False)
                and getattr(proof, "protection_normal", False)
                and getattr(proof, "lease_disarmed", False)):
            raise RuntimeError("adapter returned incomplete independent OFF/disarm proof")
        print("D061 independent HA/native OFF and lease disarm verified")
        return 0
    except BaseException as exc:
        print(f"D061 emergency OFF failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
