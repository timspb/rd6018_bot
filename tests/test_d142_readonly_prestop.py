from __future__ import annotations
import time
import unittest
from unittest.mock import patch
from tools.d142_readonly_prestop import validate_snapshot
import node104_d090_release as release


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


if __name__ == "__main__":
    unittest.main()
