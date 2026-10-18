"""D108: actual accepted session + native programmed-current binding, read-only."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import time
import unittest

from runtime.charge.strategy.main_guard_admission import (
    admit_main_guard_shadow, read_canonical_session,
)
from runtime.charge.strategy.main_guard_shadow import MainGuardShadow

SID = "a"*32
NOW = 1790000000.0


class MainGuardAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.controller = SimpleNamespace(
            is_active=True, battery_type="EFB", STAGE_MAIN="Main Charge",
            current_stage="Main Charge", _v2_trace_session_id=SID,
            _v2_battery_id="battery-01", _v2_trace_started_at=NOW-600,
            ah_capacity=70,
        )
        self.doc = {
            "v2_authoritative": True, "v2_trace_session_id": SID,
            "v2_battery_id": "battery-01", "v2_trace_started_at": NOW-600,
            "saved_at": NOW-10, "stage": "Main Charge", "profile": "EFB",
            "ah_limit": 70, "target_current": 7.0,
            "output_intent": "off",  # terminal-intent fallback is not R18
        }
        self.live = {
            "output_state_code_v2": 1, "current": 4.0,
            "set_current_readback_v2": 7.0, "ocp_readback_v2": 7.1,
        }
        self.live["_meta"] = {
            key: {"status": "ok", "age_s": 0.2}
            for key in self.live
        }

    def admit(self):
        return admit_main_guard_shadow(controller=self.controller,
                                       session_document=self.doc, live=self.live,
                                       now_epoch_s=NOW)

    def test_real_canonical_identity_and_native_current_admit_efb(self):
        value = self.admit()
        self.assertIsNotNone(value)
        self.assertEqual((value.session_id,value.battery_id), (SID,"battery-01"))
        self.assertEqual(value.recipe_initial_current_a,7.0)

    def test_caca_supported_and_agm_never_admitted(self):
        self.controller.battery_type = self.doc["profile"] = "Ca/Ca"
        self.assertIsNotNone(self.admit())
        self.controller.battery_type = self.doc["profile"] = "AGM"
        self.assertIsNone(self.admit())

    def test_stale_or_forged_canonical_identity_never_admits(self):
        mutations = [
            ("v2_authoritative",False), ("v2_trace_session_id","wrong"),
            ("v2_battery_id","other"), ("v2_trace_started_at",NOW-1200),
            ("saved_at",NOW-150), ("saved_at",NOW+2),
            ("ah_limit",80), ("stage","Mix Mode"), ("profile","AGM"),
            ("target_current",5.0), ("state","retired"),
            ("main_current_guard_v1",{}),
        ]
        for key,value in mutations:
            with self.subTest(field=key,value=value):
                self.doc[key] = value
                self.assertIsNone(self.admit())
                self.doc = {
                    "v2_authoritative": True, "v2_trace_session_id": SID,
                    "v2_battery_id":"battery-01","v2_trace_started_at":NOW-600,
                    "saved_at":NOW-10,"stage":"Main Charge","profile":"EFB",
                    "ah_limit":70,"target_current":7.0,"output_intent":"off",
                }

    def test_live_programming_must_match_durable_recipe(self):
        for key,value in [
            ("set_current_readback_v2",7.3), ("set_current_readback_v2",None),
            ("ocp_readback_v2",6.5), ("output_state_code_v2",0),
        ]:
            with self.subTest(field=key):
                saved=self.live[key]
                self.live[key]=value
                self.assertIsNone(self.admit())
                self.live[key]=saved
        self.controller.ah_capacity=100
        self.assertIsNone(self.admit())

    def test_native_freshness_must_cover_all_required_registers(self):
        for key in ("output_state_code_v2","current","set_current_readback_v2","ocp_readback_v2"):
            with self.subTest(key=key):
                original=self.live["_meta"][key]
                self.live["_meta"][key]={"status":"ok","age_s":30}
                self.assertIsNone(self.admit())
                self.live["_meta"][key]=original
        self.live.pop("_meta")
        self.assertIsNone(self.admit())

    def test_missing_file_corrupt_file_and_symlink_do_not_create_identity(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/"charge_session.json"
            self.assertIsNone(read_canonical_session(path))
            path.write_text("not-json")
            self.assertIsNone(read_canonical_session(path))
            path.write_text(json.dumps(self.doc))
            self.assertEqual(read_canonical_session(path)["v2_trace_session_id"],SID)
            path.unlink()
            target=Path(root)/"other.json"
            target.write_text(json.dumps(self.doc))
            path.symlink_to(target)
            self.assertIsNone(read_canonical_session(path))

    def test_actual_shadow_accumulates_and_invalid_binding_breaks_continuity(self):
        holder=MainGuardShadow()
        for t in range(0, 1801, 30):
            self.doc["saved_at"]=NOW+t-2
            admission=admit_main_guard_shadow(controller=self.controller,
                session_document=self.doc,live=self.live,now_epoch_s=NOW+t)
            self.assertIsNotNone(admission)
            proposal=holder.observe(
                now_s=t,session_id=admission.session_id,battery_id=admission.battery_id,
                chemistry="EFB",capacity_ah=admission.capacity_ah,
                recipe_current_a=admission.recipe_initial_current_a,
                stage="MAIN",output_on=True,output_current_a=4.0,fresh=True)
        self.assertIsNotNone(proposal)
        self.assertEqual(proposal.target_limit_a,5.0)
        self.assertEqual(holder.guard.hardware_limit_a,7.0)  # zero actuation
        holder.invalidate_evidence(now_s=1810)
        self.assertIsNone(holder.proposal)
        self.assertEqual(holder.guard.hardware_limit_a,7.0)

    def test_runtime_binding_calls_only_shadow_inside_owner(self):
        source=(Path(__file__).resolve().parents[1]/"runtime/production_runtime.py").read_text()
        self.assertIn("admit_main_guard_shadow(",source)
        self.assertIn("read_canonical_session(SESSION_FILE)",source)
        self.assertNotIn("execute_main_current_guard_reduction(",source)


if __name__ == "__main__":
    unittest.main()
