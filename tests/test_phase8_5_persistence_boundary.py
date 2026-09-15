"""Phase 8.5 persistence boundary tests; no runtime integration."""

from __future__ import annotations

import ast
from pathlib import Path
import unittest

from application.persistence_boundary import (
    InMemoryPersistenceProvider,
    PersistenceKind,
    PersistenceRecord,
    RestoreRejected,
    StateSnapshot,
)


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "application" / "persistence_boundary.py"


class PersistenceBoundaryTests(unittest.TestCase):
    def _domain_record(self, state_type: str = "session_candidate") -> PersistenceRecord:
        snapshot = StateSnapshot.new(
            state_type=state_type,
            owner="Session Domain",
            session_id="session-1",
            payload={"status": "active", "profile": "AGM"},
        )
        return PersistenceRecord("record-1", PersistenceKind.DOMAIN_STATE, snapshot)

    def test_save_load_and_candidate_restore(self) -> None:
        provider = InMemoryPersistenceProvider()
        record = self._domain_record()
        provider.save(record)
        self.assertIs(provider.load("record-1"), record)
        candidate = provider.restore_candidate(record)
        self.assertEqual(record.snapshot, candidate.snapshot)
        self.assertTrue(candidate.requires_fresh_verification)
        self.assertFalse(candidate.verified)

    def test_invalid_state_and_ownership_rejected(self) -> None:
        provider = InMemoryPersistenceProvider()
        safety = self._domain_record("active_containment")
        with self.assertRaises(RestoreRejected):
            provider.restore_candidate(safety)

        foreign = PersistenceRecord(
            "record-foreign",
            PersistenceKind.DOMAIN_STATE,
            StateSnapshot.new(state_type="session_candidate", owner="UI", payload={}),
        )
        with self.assertRaises(ValueError):
            provider.save(foreign)

    def test_historical_data_is_not_restore_candidate(self) -> None:
        provider = InMemoryPersistenceProvider()
        record = PersistenceRecord(
            "history-1",
            PersistenceKind.HISTORICAL_DATA,
            StateSnapshot.new(state_type="telemetry_history", owner="Telemetry History", payload={"items": []}),
        )
        provider.save(record)
        with self.assertRaises(RestoreRejected):
            provider.restore_candidate(record)

    def test_contracts_are_immutable(self) -> None:
        snapshot = StateSnapshot.new(state_type="fsm_state", owner="Charge Domain", payload={"state": "main"})
        with self.assertRaises(TypeError):
            snapshot.payload["state"] = "done"  # type: ignore[index]

    def test_no_infrastructure_or_decision_imports(self) -> None:
        tree = ast.parse(MODULE.read_text(encoding="utf-8"), filename=str(MODULE))
        forbidden = ("ha", "esp", "telegram", "transport", "physical", "controller", "safety", "charge_engine")
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name.lower() for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append((node.module or "").lower())
        self.assertEqual([], [name for name in imports if any(item in name for item in forbidden)])
        text = MODULE.read_text(encoding="utf-8").lower()
        for call in ("output_on", "output_off", "controller.start", "controller.stop"):
            self.assertNotIn(call, text)

    def test_document_declares_restore_boundary(self) -> None:
        text = (ROOT / "docs" / "RD6018_PERSISTENCE_ADAPTER_MODEL.md").read_text(encoding="utf-8")
        for phrase in ("StateSnapshot", "PersistenceRecord", "RestoreCandidate", "fresh runtime verification", "cannot be restored directly"):
            self.assertIn(phrase, text)


if __name__ == "__main__":
    unittest.main()
