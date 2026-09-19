import ast
import unittest
from pathlib import Path

from application.manual_session_identity_contract import (
    ManualIdentityOrigin,
    ManualSessionEvent,
    ManualSessionEventBridge,
    ManualSessionIdentityBoundaryContract,
    RestoreResolution,
)
from v3_core.canonical_events import EventType


ROOT = Path(__file__).resolve().parents[1]


class Workstream26ManualIdentityBoundaryTests(unittest.TestCase):
    def identity(self):
        return ManualSessionIdentityBoundaryContract().new_start(session_id="s1", trace_id="t1", created_at=10, source="manual_start", profile="Baic72")

    def test_identity_contract_for_start_and_resume(self):
        contract = ManualSessionIdentityBoundaryContract()
        identity = self.identity()
        resumed = contract.resumed(session_id="s2", trace_id="t2", created_at=20, source="manual_resume", profile="Baic72", linked_session_id="s1")
        self.assertEqual(ManualIdentityOrigin.MANUAL_START, identity.origin)
        self.assertEqual((ManualIdentityOrigin.RESUMED, "s1"), (resumed.origin, resumed.linked_session_id))

    def test_restore_existing_identity(self):
        result = ManualSessionIdentityBoundaryContract().restore({"session_id": "s1", "trace_id": "t1", "started_at": 10, "battery_id": "Baic72"}, now=20)
        self.assertEqual(RestoreResolution.RESTORE_EXISTING, result.resolution)
        self.assertEqual("s1", result.identity.session_id)

    def test_legacy_restore_is_ambiguous_not_guessed(self):
        result = ManualSessionIdentityBoundaryContract().restore({"state": "active", "started_at": 10, "battery_id": "Baic72"}, now=20)
        self.assertEqual(RestoreResolution.AMBIGUOUS, result.resolution)
        self.assertIsNone(result.identity)

    def test_event_bridge_requires_identity_and_maps_explicit_event(self):
        bridge = ManualSessionEventBridge()
        event = bridge.to_canonical(ManualSessionEvent("SessionStarted", 10, self.identity(), reason="operator", telemetry_ref="tel-1"), event_id="e1")
        self.assertEqual((EventType.SESSION_STARTED, "s1", "t1"), (event.event_type, event.session_id, event.trace_id))
        with self.assertRaises(ValueError):
            bridge.to_canonical(ManualSessionEvent("SessionStarted", 10, None), event_id="e2")

    def test_no_runtime_or_physical_side_effects(self):
        source = (ROOT / "application" / "manual_session_identity_contract.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports = {node.names[0].name for node in ast.walk(tree) if isinstance(node, ast.Import) and node.names}
        self.assertFalse(imports & {"aiohttp", "aioesphomeapi", "paramiko", "requests", "serial"})
        for token in ("open(", "os.replace", "controller.start", "controller.stop", "output_on", "output_off", "lease_renew"):
            self.assertNotIn(token, source)


if __name__ == "__main__":
    unittest.main()
