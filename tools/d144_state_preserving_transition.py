"""D144 state-preserving production transaction engine, owned by D090Transaction.

No CLI. The only caller must hold the existing D090 transaction lock, bind
the exact reviewed D137/D138 identities, and provide the native physical
proofs and service adapter. Legacy D090 journal is always read-only.
"""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import uuid

from tools.node104_d090_transaction import _atomic_json, _durable_tree, _sync_dir, inventory

JOURNAL = "D144_TRANSACTION.json"
PARTS = ("app", "venv")
PHASES = ("PREPARED", "BACKUP_DURABLE", "STOPPED",
          "OLD_APP_RENAMED", "NEW_APP_RENAMED",
          "OLD_VENV_RENAMED", "NEW_VENV_RENAMED", "STARTED",
          "COMMITTED", "RESTORED")


class TransitionError(RuntimeError):
    pass


class OwnerTransition:
    def __init__(self, root: Path, service, *, candidate: Path,
                 evidence, expected_before: dict, expected_candidate: dict,
                 legacy_journal_sha256: str, failpoint=None):
        self.root, self.service, self.candidate = root, service, candidate
        self.evidence = evidence
        self.expected_before = expected_before
        self.expected_candidate = expected_candidate
        self.legacy_hash = legacy_journal_sha256
        self.failpoint = failpoint or (lambda _: None)
        self.journal = root / JOURNAL

    def _phase(self, record, phase):
        record["phase"] = phase
        _atomic_json(self.journal, record)
        self.failpoint(phase)

    def _verify_legacy(self):
        from tools.node104_d090_transaction import digest
        p = self.root / "D090_TRANSACTION.json"
        if p.is_symlink() or not p.is_file() or digest(p) != self.legacy_hash:
            raise TransitionError("historical D090 journal drift; refuse transition")
        try:
            record = json.loads(p.read_text())
        except (OSError, ValueError) as e:
            raise TransitionError("historical D090 unreadable") from e
        if record.get("phase") != "STARTED" or "candidate_inventory" in record:
            raise TransitionError("unexpected historical D090 transaction state")

    def _component(self, name):
        path = self.root / name
        if path.is_symlink() or not path.is_dir():
            raise TransitionError("unsafe component: " + name)
        return path

    def _preflight(self):
        if self.root.is_symlink() or self.candidate.is_symlink():
            raise TransitionError("symlink root or candidate")
        if not self.root.is_dir() or not self.candidate.is_dir():
            raise TransitionError("missing root or candidate")
        if self.root.stat().st_dev != self.candidate.stat().st_dev:
            raise TransitionError("cross-filesystem candidate")
        self._verify_legacy()
        for name in PARTS:
            if inventory(self._component(name)) != self.expected_before[name]:
                raise TransitionError("live installed component drift: " + name)
            if inventory(self.candidate / name) != self.expected_candidate[name]:
                raise TransitionError("candidate component drift: " + name)
        state = self._component("state")
        if self.journal.exists() or self.journal.is_symlink():
            raise TransitionError("new transaction already recorded")
        if (self.root / "d144-backup").exists():
            raise TransitionError("backup name already occupied")
        if not self.service.active():
            raise TransitionError("service not active")
        self.evidence(require_stopped=False)
        return state

    def run(self):
        self._preflight()
        record = {"schema": "D144_STATE_PRESERVING_V1",
                  "phase": "PREPARED",
                  "transaction": uuid.uuid4().hex,
                  "before": self.expected_before,
                  "candidate": self.expected_candidate,
                  "legacy_sha256": self.legacy_hash,
                  "backup": "d144-backup"}
        _atomic_json(self.journal, record)
        self.failpoint("PREPARED")
        backup = self.root / "d144-backup"
        backup.mkdir(mode=0o700)
        for name in PARTS:
            shutil.copytree(self.root / name, backup / name, symlinks=True)
        _durable_tree(backup)
        self._verify_backup(record)
        self._phase(record, "BACKUP_DURABLE")
        # Validate again immediately before stopping; no stale proof reuse.
        self._verify_legacy()
        self.evidence(require_stopped=False)
        self.service.stop()
        if self.service.main_pid() != 0:
            raise TransitionError("service did not stop")
        self._phase(record, "STOPPED")
        self.evidence(require_stopped=True)
        for name in PARTS:
            self._component(name).rename(self.root / ("d144-old-" + name))
            _sync_dir(self.root)
            self.failpoint("AFTER_OLD_" + name.upper() + "_RENAME_BEFORE_JOURNAL")
            self._phase(record, "OLD_" + name.upper() + "_RENAMED")
            (self.candidate / name).rename(self.root / name)
            _sync_dir(self.root)
            self.failpoint("AFTER_NEW_" + name.upper() + "_RENAME_BEFORE_JOURNAL")
            self._phase(record, "NEW_" + name.upper() + "_RENAMED")
        for name in PARTS:
            if inventory(self._component(name)) != record["candidate"][name]:
                raise TransitionError("installed candidate bytes changed")
        self.service.start()
        self._phase(record, "STARTED")
        self.evidence(require_stopped=False)
        if not self.service.stable():
            raise TransitionError("new service not positively stable")
        self._verify_legacy()
        self._phase(record, "COMMITTED")
        return record

    def _verify_backup(self, record):
        backup = self.root / record["backup"]
        if backup.is_symlink() or not backup.is_dir():
            raise TransitionError("durable backup missing")
        for name in PARTS:
            p = backup / name
            if p.is_symlink() or not p.is_dir() or inventory(p) != record["before"][name]:
                raise TransitionError("durable backup corrupted: " + name)
        return backup

    def recover(self):
        if not self.journal.is_file() or self.journal.is_symlink():
            raise TransitionError("D144 journal missing or unsafe")
        record = json.loads(self.journal.read_text())
        if (record.get("schema") != "D144_STATE_PRESERVING_V1"
                or record.get("phase") not in PHASES
                or record.get("backup") != "d144-backup"
                or record.get("legacy_sha256") != self.legacy_hash
                or record.get("before") != self.expected_before):
            raise TransitionError("D144 journal identity invalid")
        self._verify_legacy()
        if record["phase"] == "RESTORED":
            return record
        backup = self._verify_backup(record)
        self.evidence(require_stopped=self.service.main_pid() == 0)
        if self.service.main_pid() != 0:
            self.service.stop()
            if self.service.main_pid() != 0:
                raise TransitionError("service refused stop during recovery")
        self.evidence(require_stopped=True)
        for name in PARTS:
            installed = self.root / name
            old = self.root / ("d144-old-" + name)
            if old.exists():
                if old.is_symlink() or not old.is_dir() or inventory(old) != record["before"][name]:
                    raise TransitionError("old directory corrupted: " + name)
            if installed.exists():
                if installed.is_symlink() or not installed.is_dir():
                    raise TransitionError("unsafe installed component")
                shutil.rmtree(installed)
            if old.exists():
                old.rename(installed)
            else:
                shutil.copytree(backup / name, installed, symlinks=True)
            _sync_dir(self.root)
            if inventory(installed) != record["before"][name]:
                raise TransitionError("restored bytes mismatch: " + name)
        # Never alter state, legacy journal, or deployment marker.
        self.service.start()
        if not self.service.stable():
            raise TransitionError("restored service not stable")
        self._phase(record, "RESTORED")
        return record
