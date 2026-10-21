import unittest
from tools.node104_release_admission import classify

class D124AdmissionTests(unittest.TestCase):
    def test_docs_only_does_not_demand_physical_recertification(self):
        a=classify(["docs/README.md"])
        self.assertEqual(a.classification,"python_noncontrol_change")
        self.assertFalse(a.requires_operator_signature)
        self.assertFalse(a.requires_repeat_all_physical_cases)
        self.assertTrue(a.requires_fresh_native_off)
    def test_controller_requires_targeted_acceptance_not_entire_d065(self):
        a=classify(["application/execution_port.py","runtime/charge/runtime/recovery_scaffold.py"])
        self.assertEqual(a.classification,"python_control_change")
        self.assertTrue(a.requires_targeted_control_validation)
        self.assertTrue(a.requires_d090_rollback)
        self.assertFalse(a.requires_repeat_all_physical_cases)
    def test_firmware_change_requires_hardware_validation(self):
        a=classify(["esphome/rd6018.yaml"])
        self.assertEqual(a.classification,"firmware_physical_change")
        self.assertTrue(a.requires_repeat_all_physical_cases)
    def test_operator_firmware_identity_does_not_force_repeat(self):
        self.assertFalse(classify(["bot.py"],firmware_version_changed=False).requires_repeat_all_physical_cases)
    def test_reject_ambiguous_inventory(self):
        for paths in ([],["../x"],["/etc/passwd"]):
            with self.assertRaises(ValueError):classify(paths)
