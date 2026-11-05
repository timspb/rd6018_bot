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
INSTALLED_IDENTITY = "D144_INSTALLED_RELEASE.json"
PARTS = ("app", "venv")
PHASES = ("PREPARED", "BACKUP_DURABLE", "STOPPED",
          "OLD_APP_RENAMED", "NEW_APP_RENAMED",
          "OLD_VENV_RENAMED", "NEW_VENV_RENAMED", "STARTED",
          "COMMITTED", "RESTORED")


def transaction_slot(root: Path) -> int:
    """Return the next append-only D144 slot; never recycle old evidence."""
    root = Path(root)
    found = []
    for path in root.glob("D144_TRANSACTION*.json"):
        if path.is_symlink() or not path.is_file():
            raise TransitionError("unsafe D144 transaction history entry")
        name = path.name
        if name == JOURNAL:
            slot = 1
        else:
            suffix = name.removeprefix("D144_TRANSACTION_").removesuffix(".json")
            if not suffix.isdigit() or str(int(suffix)) != suffix:
                raise TransitionError("unknown D144 transaction history name")
            slot = int(suffix)
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise TransitionError("D144 transaction history unreadable") from exc
        if (record.get("schema") != "D144_STATE_PRESERVING_V1"
                or record.get("phase") not in ("COMMITTED", "RESTORED")):
            raise TransitionError("unfinished D144 history requires recovery")
        found.append(slot)
    if not found:
        return 1
    if sorted(found) != list(range(1, max(found) + 1)):
        raise TransitionError("D144 transaction history has a slot gap")
    return max(found) + 1


class TransitionError(RuntimeError):
    pass


class OwnerTransition:
    def __init__(self, root: Path, service, *, candidate: Path,
                 evidence, expected_before: dict, expected_candidate: dict,
                 legacy_journal_sha256: str, candidate_stable, restored_stable,
                 release_identity: dict, failpoint=None, slot: int = 1):
        self.root, self.service, self.candidate = root, service, candidate
        self.evidence = evidence
        self.expected_before = expected_before
        self.expected_candidate = expected_candidate
        self.legacy_hash = legacy_journal_sha256
        self.failpoint = failpoint or (lambda _: None)
        self.candidate_stable = candidate_stable
        self.restored_stable = restored_stable
        self.release_identity = release_identity
        if type(slot) is not int or slot < 1:
            raise TransitionError("invalid D144 transaction slot")
        self.slot = slot
        suffix = "" if slot == 1 else "_" + str(slot)
        self.identity_path = root / (INSTALLED_IDENTITY.removesuffix(".json") + suffix + ".json")
        self.journal = root / (JOURNAL.removesuffix(".json") + suffix + ".json")
        self.backup_name = "d144-backup" if slot == 1 else "d144-backup-" + str(slot)

    def _old_name(self, part):
        return "d144-old-" + part if self.slot == 1 else "d144-old-" + str(self.slot) + "-" + part

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
        if (type(self.release_identity) is not dict or
                self.release_identity.get("schema") != "D144_RELEASE_IDENTITY_V1" or
                type(self.release_identity.get("source_sha")) is not str or
                len(self.release_identity["source_sha"]) != 40 or
                type(self.release_identity.get("candidate_identity_sha256")) is not str or
                len(self.release_identity["candidate_identity_sha256"]) != 64):
            raise TransitionError("reviewed release identity missing")
        if self.identity_path.exists() or self.identity_path.is_symlink():
            raise TransitionError("installed release identity already exists")
        for name in PARTS:
            if inventory(self._component(name)) != self.expected_before[name]:
                raise TransitionError("live installed component drift: " + name)
            if inventory(self.candidate / name) != self.expected_candidate[name]:
                raise TransitionError("candidate component drift: " + name)
        state = self._component("state")
        if self.journal.exists() or self.journal.is_symlink():
            raise TransitionError("new transaction already recorded")
        if ((self.root / self.backup_name).exists()
                or (self.root / self.backup_name).is_symlink()):
            raise TransitionError("backup name already occupied")
        for name in PARTS:
            old = self.root / self._old_name(name)
            if old.exists() or old.is_symlink():
                raise TransitionError("rollback component name already occupied")
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
                  "backup": self.backup_name,
                  "slot": self.slot,
                  "release_identity": self.release_identity}
        _atomic_json(self.journal, record)
        self.failpoint("PREPARED")
        backup = self.root / self.backup_name
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
            self._component(name).rename(self.root / self._old_name(name))
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
        if not self.candidate_stable():
            raise TransitionError("new service not positively stable")
        self._verify_legacy()
        identity = dict(self.release_identity)
        identity["transaction"] = record["transaction"]
        _atomic_json(self.identity_path, identity)
        self.failpoint("AFTER_IDENTITY_BEFORE_COMMIT")
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
                or record.get("backup") != self.backup_name
                or record.get("slot", self.slot) != self.slot
                or record.get("legacy_sha256") != self.legacy_hash
                or record.get("before") != self.expected_before
                or record.get("release_identity") != self.release_identity):
            raise TransitionError("D144 journal identity invalid")
        self._verify_legacy()
        if self.identity_path.exists() or self.identity_path.is_symlink():
            expected_identity = dict(self.release_identity)
            expected_identity["transaction"] = record["transaction"]
            if (self.identity_path.is_symlink() or not self.identity_path.is_file()
                    or json.loads(self.identity_path.read_text()) != expected_identity):
                raise TransitionError("installed release identity drift")
        if record["phase"] == "RESTORED":
            return record
        # Crash after PREPARED, before a durable backup: no service stop or
        # rename has been authorized. Only settle if the exact original bytes
        # and the original running service can be positively verified.
        backup_path = self.root / record["backup"]
        if (record["phase"] == "PREPARED"
                and not backup_path.exists() and not backup_path.is_symlink()):
            for name in PARTS:
                if inventory(self._component(name)) != record["before"][name]:
                    raise TransitionError("PREPARED original preimage drift")
            if not self.service.active() or self.service.main_pid() <= 0:
                raise TransitionError("PREPARED service not positively running")
            self.evidence(require_stopped=False)
            if not self.restored_stable():
                raise TransitionError("PREPARED original service stability unproved")
            self._phase(record, "RESTORED")
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
            old = self.root / self._old_name(name)
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
        if not self.restored_stable():
            raise TransitionError("restored service not stable")
        if self.identity_path.is_file():
            self.identity_path.unlink()
            _sync_dir(self.root)
        self._phase(record, "RESTORED")
        return record
