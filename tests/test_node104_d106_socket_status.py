"""D106 read-only physical-test status contract; no live socket used."""
import copy
import unittest
from tools.node104_d106_readonly_socket import validate_status, StatusError


class D106SocketStatusTests(unittest.TestCase):
    def receipt(self):
        return {"ok": True, "operation": "autonomous_status",
                "result": {"rd_control_mode": "pb_managed",
                           "manager_edge_autonomous": False,
                           "edge_autonomous": False,
                           "output_state_code_v2": 0.0,
                           "protection_code": 0,
                           "programmed_values": {
                               "set_voltage": 13.57, "set_current": .1,
                               "ovp": 14.07, "ocp": .2},
                           "edge_lease": {"armed": False, "tripped": False,
                                          "boot_quarantine": False, "remaining_s": 0,
                                          "modbus_age_s": 1.0, "generation": 4},
                           "rd_actuator_writes_injected": 0}}

    def test_status_read_only_receipt(self):
        self.assertEqual("pb_managed", validate_status(self.receipt())["rd_control_mode"])

    def test_status_denies_unsafe_missing_ambiguous_fields(self):
        def change(path, bad):
            r=self.receipt()
            obj=r
            for part in path[:-1]:
                obj=obj[part]
            obj[path[-1]]=bad
            with self.assertRaises(StatusError):
                validate_status(r)
        for path, bad in (
            (["ok"], False), (["operation"], "enter_autonomous_verified_off"),
            (["result", "rd_control_mode"], "hands_off"),
            (["result", "edge_autonomous"], True),
            (["result", "manager_edge_autonomous"], True),
            (["result", "output_state_code_v2"], 1.0),
            (["result", "protection_code"], 2),
            (["result", "edge_lease", "armed"], True),
            (["result", "edge_lease", "remaining_s"], 1),
            (["result", "edge_lease", "modbus_age_s"], 25),
            (["result", "programmed_values", "set_voltage"], 17.3),
            (["result", "programmed_values", "set_current"], .9),
            (["result", "programmed_values", "ocp"], .01),
            (["result", "rd_actuator_writes_injected"], 1),
            (["result", "rd_actuator_writes_injected"], False),
            (["result", "rd_actuator_writes_injected"], 0.0),
        ):
            with self.subTest(path=path):
                change(path,bad)
        for part in ("programmed_values", "edge_lease"):
            r=self.receipt()
            del r["result"][part]
            with self.assertRaises(StatusError):
                validate_status(r)
