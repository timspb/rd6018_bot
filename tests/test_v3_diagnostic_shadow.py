import unittest

from runtime.diagnostics import DiagnosticAuthority, LegacyDiagnosticAdapter


class DiagnosticShadowTests(unittest.TestCase):
    def test_maps_confirmed_legacy_assessment(self):
        decision = LegacyDiagnosticAdapter.to_decision({
            "authority": "block_automatic_hv",
            "authority_reasons": ("multi_signal",),
            "independent_cell_fault_classes": {"rested_ocv", "load_test"},
        })
        self.assertEqual(decision.authority, DiagnosticAuthority.BLOCK_AUTOMATIC_HV)
        self.assertEqual(decision.hypothesis, "cell_fault")
        self.assertIn("multi_signal", decision.reasons)

    def test_unknown_authority_fails_conservatively(self):
        decision = LegacyDiagnosticAdapter.to_decision({"authority": "unknown"})
        self.assertEqual(decision.authority, DiagnosticAuthority.VERIFY_BEFORE_HV)


if __name__ == "__main__":
    unittest.main()
