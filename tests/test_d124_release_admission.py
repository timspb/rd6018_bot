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
    def test_d090_owner_calls_admission_before_staging_and_activation(self):
        from pathlib import Path
        root=Path(__file__).resolve().parents[1]
        code=(root/'tools/node104_d090_transaction.py').read_text()
        prepare=code[code.index('    def prepare(self, staged_release:'):code.index('    def _baseline(self)')]
        activate=code[code.index('    def activate(self, staged_release:'):code.index('    def _assert_candidate(',code.index('    def activate(self, staged_release:'))]
        self.assertLess(prepare.index('self.release_admission()'),prepare.index('self._layout()'))
        self.assertLess(activate.index('self.release_admission()'),activate.index('self._layout()'))
        self.assertIn('self.release_admission = release_admission or',code)

    def test_d090_owner_calls_admission_before_staging_and_activation(self):
        from pathlib import Path
        root=Path(__file__).resolve().parents[1]
        code=(root/'tools/node104_d090_transaction.py').read_text()
        prepare=code[code.index('    def prepare(self, staged_release:'):code.index('    def _baseline(self)')]
        activate=code[code.index('    def activate(self, staged_release:'):code.index('    def _assert_candidate(',code.index('    def activate(self, staged_release:'))]
        self.assertLess(prepare.index('self.release_admission()'),prepare.index('self._layout()'))
        self.assertLess(activate.index('self.release_admission()'),activate.index('self._layout()'))
        self.assertIn('self.release_admission = release_admission or',code)

    def test_reject_ambiguous_inventory(self):
        for paths in ([],["../x"],["/etc/passwd"]):
            with self.assertRaises(ValueError):classify(paths)
