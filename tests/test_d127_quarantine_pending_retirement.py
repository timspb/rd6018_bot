"""Regression for retiring a quarantined unresolved MAIN current/OCP proposal.

No hardware calls: all inputs are persisted snapshots and mocked owner state.
"""
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from application.controller_session_retirement import _ControllerSessionRetirement
from runtime.charge.strategy.main_current_guard import MainCurrentGuard, PendingProposal
from runtime.charge.strategy.main_guard_session import _digest, GUARD_KEY


class Controller:
    STAGE_MAIN = "Main Charge"
    STAGE_IDLE = "Idle"
    current_stage = "Idle"
    _v2_trace_session_id = None
    _v2_battery_id = None


class Journal:
    def __init__(self, incident):
        self.incident = incident

    def incident_binding(self):
        return self.incident


class QuarantinedPendingRetirementTests(unittest.TestCase):
    def test_pending_requires_matching_exact_quarantine(self):
        guard = MainCurrentGuard.start(
            session_id="session-1", battery_id="battery-1",
            segment_id="session-1:MAIN", capacity_ah=72.0,
            recipe_initial_current_a=7.2, now_s=200.0)
        guard = replace(
            guard, hardware_limit_a=1.24, proposal_sequence=2,
            pending=PendingProposal("proposal-2", 1.22, 200.0, 320.0))
        snapshot = guard.snapshot()
        document = {
            "profile": "Ca/Ca", "stage": "Main Charge", "ah_limit": 72,
            "v2_trace_session_id": "session-1", "v2_battery_id": "battery-1",
            GUARD_KEY: {"journal_schema": 1, "revision": 117,
                        "snapshot": snapshot, "sha256": _digest(snapshot)},
        }
        incident = {
            "session_id": "session-1", "battery_id": "battery-1",
            "incident_id": "incident-1",
            "reason": "main_guard_current_ocp_transaction_unconfirmed:postflight_guard_ack_rejected",
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "session.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            port = SimpleNamespace(
                session_recovery_guard=SimpleNamespace(quarantined=True))
            journal = Journal(incident)
            app = SimpleNamespace(
                charge_controller=Controller(), execution_port=port,
                recovery_quarantine_journal=journal)
            retirement = _ControllerSessionRetirement(app, str(path))
            self.assertTrue(retirement.validate(incident))
            port.session_recovery_guard.quarantined = False
            self.assertFalse(retirement.validate(incident))
            port.session_recovery_guard.quarantined = True
            for wrong in (
                {**incident, "incident_id": "other"},
                {**incident, "battery_id": "other"},
                {**incident, "reason": "unrelated_quarantine"},
            ):
                journal.incident = wrong
                self.assertFalse(retirement.validate(incident))
            journal.incident = incident
            damaged = json.loads(json.dumps(document))
            damaged[GUARD_KEY]["sha256"] = "invalid"
            path.write_text(json.dumps(damaged), encoding="utf-8")
            self.assertFalse(retirement.validate(incident))
            path.write_text(json.dumps(document), encoding="utf-8")
            damaged = json.loads(json.dumps(document))
            damaged[GUARD_KEY]["snapshot"]["fault"] = "current_guard_fault"
            damaged[GUARD_KEY]["sha256"] = _digest(damaged[GUARD_KEY]["snapshot"])
            path.write_text(json.dumps(damaged), encoding="utf-8")
            self.assertFalse(retirement.validate(incident))


if __name__ == "__main__":
    unittest.main()
