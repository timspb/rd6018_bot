"""D149 immutable, phase-aware D091 observer selection.

Read-only: runs pinned existing D147 and D148 collectors through the current
service virtualenv; does not control systemd, charge output, or setpoints.
Return a canonical D090 PhysicalOffProof with fresh, strict source nonces.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
from dataclasses import fields

try:
    import node104_d090_release as release
except ModuleNotFoundError:
    from tools import node104_d090_release as release

D147_SHA = "1127e9e3ba52a43ca97ddd8501ea4ac9a52887e708d725fd1299fd22d15a2398"
D148_SHA = "a738f08e5554fa70188af856bc359b198838a983394948aaee8c64fdd9df1e95"

class ObserverRouteError(RuntimeError):
    pass

class ReadOnlyObserverRouter:
    def __init__(self, root: Path, *, runner=None):
        self.root = root
        self.runner = runner or self._run
        self.phase = "PRE_STOP"
        self.calls = 0

    def select(self, phase: str) -> None:
        if phase not in ("PRE_STOP", "STOPPED", "POST_START", "RECOVERY"):
            raise ObserverRouteError("unknown physical proof phase")
        self.phase = phase

    def _run(self, cmd, env):
        return subprocess.run(cmd, check=True, capture_output=True, text=True,
                              env=env, timeout=45).stdout

    def __call__(self) -> release.PhysicalOffProof:
        phase = self.phase
        if phase == "PRE_STOP":
            file = self.root / "d147-proof/node104_d091_physical_proof_collector.py"
            expected = D147_SHA
        else:
            file = self.root / "d147-proof/d148_recovery_d091_collector.py"
            expected = D148_SHA
        parent = file.parent
        if (parent.is_symlink() or not parent.is_dir()
                or parent.stat().st_mode & 0o022
                or file.is_symlink() or not file.is_file()
                or file.stat().st_mode & 0o222):
            raise ObserverRouteError("pinned observer filesystem identity unsafe")
        h = hashlib.sha256(file.read_bytes()).hexdigest()
        if h != expected:
            raise ObserverRouteError("pinned observer digest drift")
        python = self.root / "venv/bin/python"
        if not python.is_file():
            raise ObserverRouteError("service Python runtime not available")
        env = dict(os.environ)
        env["D090_EXPECTED_ESP_VERSION"] = "2.3-ha-canonical"
        env["D090_SOFTWARE_RELEASE"] = "1"
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        if phase == "RECOVERY":
            env["D090_STATE_PRESERVING_RECOVERY"] = "1"
        else:
            env.pop("D090_STATE_PRESERVING_RECOVERY", None)
        try:
            raw = self.runner([str(python), str(file)], env)
            value = json.loads(raw)
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired,
                ValueError) as exc:
            raise ObserverRouteError("pinned observer failed; no proof") from exc
        required = {f.name for f in fields(release.PhysicalOffProof)}
        if type(value) is not dict or set(value) != required:
            raise ObserverRouteError("D090 physical proof schema drift")
        nonces = value.get("source_nonces")
        if (type(nonces) is not list or len(nonces) != 2
                or any(type(n) is not str or not n for n in nonces)
                or nonces[0] == nonces[1]):
            raise ObserverRouteError("non-independent physical proof nonces")
        value["source_nonces"] = tuple(nonces)
        self.calls += 1
        return release.PhysicalOffProof(**value)
