"""Regression: stopped MIX after MAIN must expose the existing verified-OFF retirement."""
import json
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from application.controller_session_retirement import _ControllerSessionRetirement


class OrphanMixBindingTests(unittest.TestCase):
    def test_partial_ui_controller_is_not_orphan_authority(self):
        controller = types.SimpleNamespace(is_active=False)
        app = types.SimpleNamespace(charge_controller=controller)
        doc = {"stage": "Mix Mode", "v2_trace_session_id": "S1",
               "v2_battery_id": "B1", "main_current_guard_v1": {}}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "session.json"
            path.write_text(json.dumps(doc), encoding="utf8")
            retirement = _ControllerSessionRetirement(app, str(path))
            self.assertIsNone(retirement.orphan_binding())

    def test_interrupted_mix_is_retirable_but_unrelated_mix_is_not(self):
        controller = types.SimpleNamespace(STAGE_MAIN="Main Charge", STAGE_MIX="Mix Mode",
            STAGE_IDLE="Idle", current_stage="Idle", _v2_trace_session_id=None,
            _v2_battery_id=None)
        app = types.SimpleNamespace(charge_controller=controller)
        doc = {"stage":"Mix Mode", "v2_trace_session_id":"S1", "v2_battery_id":"B1",
            "main_current_guard_v1":{}, "stage_history":[{"from":"Main Charge","to":"Mix Mode"}]}
        guard = types.SimpleNamespace(pending=None, fault=None)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/"session.json"
            path.write_text(json.dumps(doc), encoding="utf8")
            retirement = _ControllerSessionRetirement(app, str(path))
            with patch("runtime.charge.strategy.main_guard_session.read_guard", return_value=(guard, 1)):
                binding = retirement.orphan_binding()
                self.assertEqual(binding["session_id"], "S1")
                self.assertTrue(retirement.validate(binding))
                doc["stage_history"] = []
                path.write_text(json.dumps(doc), encoding="utf8")
                self.assertIsNone(retirement.orphan_binding())
