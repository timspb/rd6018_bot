from __future__ import annotations
import time
import unittest
from unittest.mock import patch
from tools.d142_readonly_prestop import validate_snapshot
import tools.d142_readonly_prestop as d142
import node104_d090_release as release
from pathlib import Path
import tempfile


class D142Tests(unittest.TestCase):
    def proof(self):
        return {
            "captured_at_epoch": time.time(),
            "host_machine_id": release.MACHINE_ID,
            "service_main_pid": 321,
            "ha102_output_off": True,
            "ha102_voltage_v": 0.0,
            "ha102_current_a": 0.0,
            "esp128_output_off": True,
            "esp128_voltage_v": 0.0,
            "esp128_current_a": 0.0,
            "native_sensor_state_fresh": True,
            "edge_lease_armed": False,
            "edge_boot_quarantine": False,
            "physical_node_owner_count": 1,
            "active_session": False,
            "source_nonces": ["distinct-HA", "distinct-ESP"],
        }

    def test_valid_off(self):
        p = self.proof()
        validate_snapshot(p, pid=321, now=p["captured_at_epoch"])

    def test_active_session_requires_explicit_guarded_preimage_authority(self):
        p=self.proof(); p["active_session"]=True
        with self.assertRaises(release.GateError):
            validate_snapshot(p,pid=321,now=p["captured_at_epoch"])
        validate_snapshot(p,pid=321,now=p["captured_at_epoch"],allow_active_session=True)

    def test_stale_proof_fail_closed(self):
        p = self.proof()
        with self.assertRaises(release.GateError):
            validate_snapshot(p, pid=321, now=p["captured_at_epoch"] + 300)

    def test_wrong_pid_fail_closed(self):
        p = self.proof()
        with self.assertRaisesRegex(ValueError, "another process"):
            validate_snapshot(p, pid=322, now=p["captured_at_epoch"])

    def test_unsafe_output_fail_closed(self):
        p = self.proof()
        p["esp128_current_a"] = 1.0
        with self.assertRaises(release.GateError):
            validate_snapshot(p, pid=321, now=p["captured_at_epoch"])

    def test_live_hands_off_output_on_is_not_off(self):
        # A missing managed charge_session.json is NOT evidence that the
        # hardware output is off. The external charger can remain active
        # while this bot is deliberately in hands_off mode.
        proof = self.proof()
        proof["ha102_output_off"] = False
        proof["esp128_output_off"] = False
        proof["ha102_voltage_v"] = 14.67
        proof["esp128_voltage_v"] = 14.67
        proof["ha102_current_a"] = 0.05
        proof["esp128_current_a"] = 0.05
        with self.assertRaises(release.GateError):
            validate_snapshot(
                proof, pid=321, now=proof["captured_at_epoch"],
            )

    def test_ha_on_refused_even_if_esp_off(self):
        proof = self.proof()
        proof["ha102_output_off"] = False
        proof["ha102_voltage_v"] = 14.67
        proof["ha102_current_a"] = 0.05
        with self.assertRaises(release.GateError):
            validate_snapshot(proof, pid=321, now=proof["captured_at_epoch"])

    def test_esp_on_refused_even_if_ha_off(self):
        proof = self.proof()
        proof["esp128_output_off"] = False
        proof["esp128_voltage_v"] = 14.67
        proof["esp128_current_a"] = 0.05
        with self.assertRaises(release.GateError):
            validate_snapshot(proof, pid=321, now=proof["captured_at_epoch"])

    def test_duplicate_independent_nonces_refused(self):
        p = self.proof()
        p["source_nonces"] = ["same", "same"]
        with self.assertRaises(release.GateError):
            validate_snapshot(p, pid=321, now=p["captured_at_epoch"])

    def test_armed_lease_refused(self):
        p = self.proof()
        p["edge_lease_armed"] = True
        with self.assertRaises(release.GateError):
            validate_snapshot(p, pid=321, now=p["captured_at_epoch"])

    def test_fresh_d091_off_precedes_historical_guard_admission(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/"app").mkdir(); (root/"app"/"bot.py").write_text("fixture")
            stage=root/"stage"; stage.mkdir()
            proof=self.proof(); proof["active_session"]=True
            events=[]
            preimage={"preimage_sha256":"f"*64,
                      "preserved_guarded_main":{"revision":481,"last_output_on":True}}
            candidate={"candidate_identity_sha256":"a"*64,
                       "preserved_guarded_main":True,
                       "preserved_guard":{"revision":481,"last_output_on":True}}
            def collect():
                events.append("fresh_d091")
                return proof
            def observe(*args, **kwargs):
                events.append("d137")
                self.assertEqual(kwargs["physical_off_reconciliation"]["source_nonces"],
                                 proof["source_nonces"])
                return preimage
            def inspect(**kwargs):
                events.append("d138")
                self.assertIs(kwargs["observed_preimage_record"],preimage)
                return candidate
            original=Path.read_bytes
            def fake_argv(path):
                if str(path)=="/proc/321/cmdline":
                    return str(root/"app"/"bot.py").encode()+bytes([0])
                return original(path)
            with patch.object(d142,"observed_preimage",side_effect=observe), \
                 patch.object(d142,"inspect_candidate",side_effect=inspect), \
                 patch.object(d142,"require_capacity",return_value={
                     "capacity_pass":True,"observed_free_bytes":500,"minimum_free_bytes":1}), \
                 patch.object(Path,"read_bytes",fake_argv):
                result=d142.assess(root,stage,pid=321,source_sha="b"*40,
                    preimage_sha256=preimage["preimage_sha256"],collector=root/"collector",
                    collect=collect)
            self.assertEqual(events,["fresh_d091","d137","d138"])
            self.assertTrue(result["preserved_guarded_main"])

    def test_fresh_preimage_is_reported_without_static_profile_digest_comparison(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/"app").mkdir(); (root/"app"/"bot.py").write_text("fixture")
            stage=root/"stage"; stage.mkdir()
            proof=self.proof()
            preimage={"preimage_sha256":"d"*64}
            candidate={"candidate_identity_sha256":"a"*64}
            original=Path.read_bytes
            def fake_argv(path):
                if str(path)=="/proc/321/cmdline":
                    return str(root/"app"/"bot.py").encode()+bytes([0])
                return original(path)
            with patch.object(d142,"observed_preimage",return_value=preimage), \
                 patch.object(d142,"inspect_candidate",return_value=candidate) as inspect, \
                 patch.object(d142,"require_capacity",return_value={
                     "capacity_pass":True,"observed_free_bytes":500,"minimum_free_bytes":1}), \
                 patch.object(Path,"read_bytes",fake_argv):
                result=d142.assess(root,stage,pid=321,source_sha="b"*40,
                    preimage_sha256=None,collector=root/"collector",
                    collect=lambda: proof)
            self.assertEqual(result["observed_preimage_sha256"],"d"*64)
            self.assertEqual(inspect.call_args.kwargs["preimage_sha256"],"d"*64)

    def test_active_session_output_on_never_reaches_d137(self):
        proof=self.proof(); proof["active_session"]=True
        proof["esp128_output_off"]=False
        with patch.object(d142,"observed_preimage") as observe:
            with self.assertRaises(release.GateError):
                d142.assess(Path("/unused"),Path("/unused"),pid=321,
                    source_sha="b"*40,preimage_sha256="f"*64,
                    collector=Path("/unused"),collect=lambda: proof)
        observe.assert_not_called()


if __name__ == "__main__":
    unittest.main()
