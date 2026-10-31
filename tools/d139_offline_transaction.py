"""D139 isolated-only state-preserving transaction exercise.

Reuses D090 inventory, durable copy, atomic journal and directory sync helpers.
There is intentionally no production CLI/activation path. The D090 journal,
the legacy deploy marker, and state/ are never touched.
"""
from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from tools.node104_d090_transaction import (
    _atomic_json, _durable_tree, _sync_dir, inventory,
)

SENTINEL = ".D139_OFFLINE_TEST_ROOT"
JOURNAL = "D139_OFFLINE_TRANSACTION.json"
COMPONENTS = ("app", "venv")


class D139Error(RuntimeError):
    pass


class OfflineTransition:
    def __init__(self, root: Path, service, *, failpoint=None):
        self.root = root
        self.service = service
        self.failpoint = failpoint or (lambda name: None)
        if (root.is_symlink() or not root.is_dir()
                or not root.resolve().is_relative_to(Path(tempfile.gettempdir()).resolve())
                or not (root / SENTINEL).is_file()
                or getattr(service, "d139_offline_fixture", False) is not True):
            raise D139Error("D139 only permits isolated fixture roots")
        if not callable(getattr(service, "stop", None)) or not callable(getattr(service, "start", None)):
            raise D139Error("isolated service adapter missing")
        self.journal = root / JOURNAL

    def _read(self):
        if self.journal.is_symlink():
            raise D139Error("unsafe journal")
        return json.loads(self.journal.read_text())

    def _phase(self, doc, phase):
        doc["phase"] = phase
        _atomic_json(self.journal, doc)
        self.failpoint(phase)

    def _scope(self, path):
        if path.is_symlink() or not path.is_dir() or path.parent != self.root:
            raise D139Error("unsafe transaction component")

    def _check_backups(self, record):
        backup = self.root / "d139-backup"
        self._scope(backup)
        for key in COMPONENTS:
            p = backup / key
            if p.is_symlink() or not p.is_dir() or inventory(p) != record["before"][key]:
                raise D139Error("rollback preimage missing or changed")
        return backup

    def activate_fixture(self):
        if self.journal.exists():
            raise D139Error("transaction already exists")
        for name in (*COMPONENTS, "state", "d139-candidate"):
            self._scope(self.root / name)
        if not self.service.active:
            raise D139Error("fake service is not active")
        candidate = self.root / "d139-candidate"
        before = {name: inventory(self.root / name) for name in COMPONENTS}
        wanted = {name: inventory(candidate / name) for name in COMPONENTS}
        state_initial = inventory(self.root / "state")
        if (self.root / "d139-backup").exists():
            raise D139Error("existing backup")
        doc = {"schema": "D139_OFFLINE_V1", "phase": "PREPARED",
               "before": before, "candidate": wanted, "state_initial": state_initial}
        _atomic_json(self.journal, doc)
        self.failpoint("PREPARED")
        backup = self.root / "d139-backup"
        backup.mkdir()
        for key in COMPONENTS:
            shutil.copytree(self.root / key, backup / key, symlinks=True)
        _durable_tree(backup)
        self._check_backups(doc)
        self._phase(doc, "BACKUP_DURABLE")
        self.service.stop()
        self._phase(doc, "STOPPED")
        for key in COMPONENTS:
            installed = self.root / key
            previous = self.root / ("d139-old-" + key)
            installed.rename(previous)
            _sync_dir(self.root)
            self._phase(doc, "OLD_" + key.upper() + "_RENAMED")
            (candidate / key).rename(installed)
            _sync_dir(self.root)
            self._phase(doc, "NEW_" + key.upper() + "_RENAMED")
        for key in COMPONENTS:
            if inventory(self.root / key) != wanted[key]:
                raise D139Error("candidate changed during swap")
        self.service.start()
        self._phase(doc, "CANDIDATE_RUNNING")
        # A fixture cannot prove hardware admission or the production service.
        # No COMMITTED production transition is exposed.
        return doc

    def recover_fixture(self):
        if not self.journal.is_file():
            raise D139Error("journal missing")
        doc = self._read()
        if doc.get("schema") != "D139_OFFLINE_V1" or doc.get("phase") not in {
                "PREPARED", "BACKUP_DURABLE", "STOPPED",
                "OLD_APP_RENAMED", "NEW_APP_RENAMED", "OLD_VENV_RENAMED",
                "NEW_VENV_RENAMED", "CANDIDATE_RUNNING", "RESTORED"}:
            raise D139Error("invalid journal phase")
        backup = self._check_backups(doc)
        if doc["phase"] == "RESTORED":
            return doc
        self.service.stop()
        for key in COMPONENTS:
            installed = self.root / key
            old = self.root / ("d139-old-" + key)
            if installed.exists():
                self._scope(installed)
                shutil.rmtree(installed)
            if old.exists():
                self._scope(old)
                old.rename(installed)
            else:
                shutil.copytree(backup / key, installed, symlinks=True)
            _sync_dir(self.root)
            if inventory(installed) != doc["before"][key]:
                raise D139Error("rollback exact-byte verification failed")
        # Deliberately NO operation on state/ or the legacy D090 files.
        self.service.start()
        self._phase(doc, "RESTORED")
        return doc
