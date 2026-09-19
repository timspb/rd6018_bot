import ast
import json
import tempfile
import unittest
from pathlib import Path

from application.manual_identity_integration import ManualIdentityIntegrationAdapter
from application.manual_session_identity_contract import ManualIdentityOrigin
from manual_mode import ManualChargeRequest, ManualSessionManager, ManualSessionState
from v3_core.canonical_events import EventType


class Workstream28ManualIdentityIntegrationTests(unittest.TestCase):
    def test_new_manual_start_identity_and_canonical_event(self):
        adapter = ManualIdentityIntegrationAdapter()
        identity = adapter.create_for_start(profile="Baic72", created_at=10)
        event = adapter.emit(event_type=EventType.SESSION_STARTED, timestamp=11, phase_before="arming", phase_after="active", reason="safe_enable_confirmed")
        self.assertEqual(ManualIdentityOrigin.MANUAL_START, identity.origin)
        self.assertEqual((identity.session_id, identity.trace_id), (event.session_id, event.trace_id))
        self.assertEqual(EventType.SESSION_STARTED, event.event_type)

    def test_resume_existing_identity(self):
        decision = ManualIdentityIntegrationAdapter().restore({"session_id": "s1", "trace_id": "t1", "created_at": 10, "profile": "Baic72"}, now=20)
        self.assertEqual("RESTORE_EXISTING", decision.resolution.value)
        self.assertEqual("s1", decision.identity.session_id)

    def test_legacy_restore_is_ambiguous(self):
        decision = ManualIdentityIntegrationAdapter().restore({"state": "active", "started_at": 10, "battery_id": "Baic72"}, now=20)
        self.assertEqual("AMBIGUOUS", decision.resolution.value)
        self.assertIsNone(decision.identity)

    def test_persistence_payload_is_compatible_with_legacy_shape(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = ManualSessionManager(type("App", (), {})(), session_file=str(Path(directory) / "manual_session_v2.json"))
            manager.state = ManualSessionState.INTERRUPTED
            manager.request = ManualChargeRequest(14.8, 2.0, battery_id="Baic72")
            manager.identity_integration.create_for_start(profile="Baic72", created_at=10)
            document = manager._document()
            self.assertEqual(2, document["version"])
            self.assertEqual("Baic72", document["session_identity"]["profile"])
            legacy = dict(document)
            legacy.pop("session_identity")
            legacy_path = Path(directory) / "legacy.json"
            legacy_path.write_text(json.dumps(legacy), encoding="utf-8")
            restored = ManualSessionManager(type("App", (), {})(), session_file=str(legacy_path))
            self.assertEqual("AMBIGUOUS", restored.identity_restore_resolution)
            self.assertIsNone(restored.session_identity)

    def test_integration_has_no_physical_or_control_imports(self):
        source = (Path(__file__).resolve().parents[1] / "application" / "manual_identity_integration.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
        self.assertFalse(imports & {"aiohttp", "aioesphomeapi", "paramiko", "serial", "requests"})
        for token in ("controller.start", "controller.stop", "output_on", "output_off", "lease", "safe_enable_output", "turn_off"):
            self.assertNotIn(token, source)


if __name__ == "__main__":
    unittest.main()
