import unittest
from types import SimpleNamespace

from ownership_provenance import (
    EvidenceConfidence,
    OwnershipMode,
    OwnershipProvenance,
    OutputState,
    build_ownership_snapshot,
)


def _live(switch="on", autonomous_mode=None):
    live = {"switch": switch}
    if autonomous_mode is not None:
        live["autonomous_mode"] = autonomous_mode
        live["_meta"] = {"autonomous_mode": {"status": "ok"}}
    return live


class OwnershipProvenanceTests(unittest.TestCase):
    def test_managed_session_is_bot_managed(self):
        manager = SimpleNamespace(
            app=SimpleNamespace(
                charge_controller=SimpleNamespace(is_active=True),
                manual_session_manager=None,
            ),
            hands_off=False,
            edge_autonomous=False,
        )
        snapshot = build_ownership_snapshot(_live(), manager)
        self.assertEqual(snapshot.mode, OwnershipMode.PB_MANAGED)
        self.assertEqual(snapshot.provenance, OwnershipProvenance.BOT_MANAGED)
        self.assertEqual(snapshot.confidence, EvidenceConfidence.VERIFIED)

    def test_autonomous_bit_is_autonomous_evidence(self):
        manager = SimpleNamespace(hands_off=True, edge_autonomous=False)
        snapshot = build_ownership_snapshot(_live(autonomous_mode=True), manager)
        self.assertEqual(snapshot.mode, OwnershipMode.AUTONOMOUS)
        self.assertEqual(snapshot.provenance, OwnershipProvenance.AUTONOMOUS)
        self.assertEqual(snapshot.confidence, EvidenceConfidence.VERIFIED)

    def test_output_on_without_authority_is_foreign_observed(self):
        snapshot = build_ownership_snapshot(_live())
        self.assertEqual(snapshot.output, OutputState.ON)
        self.assertEqual(snapshot.provenance, OwnershipProvenance.FOREIGN_OBSERVED)
        self.assertEqual(snapshot.confidence, EvidenceConfidence.OBSERVED)

    def test_missing_telemetry_is_unknown(self):
        snapshot = build_ownership_snapshot({})
        self.assertEqual(snapshot.output, OutputState.UNKNOWN)
        self.assertEqual(snapshot.provenance, OwnershipProvenance.UNKNOWN)
        self.assertEqual(snapshot.confidence, EvidenceConfidence.UNKNOWN)

    def test_reboot_output_on_without_provenance_is_unknown(self):
        snapshot = build_ownership_snapshot({"switch": "on"}, startup_recovery=True)
        self.assertEqual(snapshot.provenance, OwnershipProvenance.UNKNOWN)
        self.assertEqual(snapshot.confidence, EvidenceConfidence.UNKNOWN)

    def test_snapshot_is_read_only(self):
        live = _live()
        manager = SimpleNamespace(hands_off=False, edge_autonomous=False)
        before = dict(live)
        build_ownership_snapshot(live, manager)
        self.assertEqual(live, before)


if __name__ == "__main__":
    unittest.main()
