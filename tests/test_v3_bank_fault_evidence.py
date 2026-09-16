import unittest

from runtime.diagnostics import (
    BankFaultEvidence, BankFaultLevel, BankFaultPolicy, BankFaultSignal,
    BatteryDiagnosticEvidence, BatteryDiagnosticsEngine, DiagnosticAuthority,
    LegacyBankFaultAdapter, score_bank_fault, SafetyEvidence,
    evaluate_safety_evidence, safety_evidence_from_diagnostic,
)


class V3BankFaultEvidenceTests(unittest.TestCase):
    def test_configurable_scoring_levels(self):
        evidence = BankFaultEvidence(tuple(
            BankFaultSignal(name, True, 100.0, "test")
            for name in ("slow_voltage_rise", "prolonged_main_duration", "low_voltage_persistent")
        ))
        score, level = score_bank_fault(evidence, BankFaultPolicy(
            weights={"slow_voltage_rise": 10, "prolonged_main_duration": 15, "low_voltage_persistent": 30},
        ))
        self.assertEqual(score, 55)
        self.assertEqual(level, BankFaultLevel.PROBABLE)

    def test_bank_evidence_becomes_cell_fault_hypothesis_only(self):
        bank = BankFaultEvidence((BankFaultSignal("low_voltage_persistent", True, 100.0, "telemetry"),))
        report = BatteryDiagnosticsEngine().evaluate(BatteryDiagnosticEvidence(), bank_fault=bank)
        self.assertEqual(report.authority.authority, DiagnosticAuthority.ALLOW)
        self.assertEqual(report.hypotheses[0].hypothesis.value, "cell_fault")

    def test_high_inferred_score_blocks_hv_but_is_not_hard_stop(self):
        bank = BankFaultEvidence(tuple(
            BankFaultSignal(name, True, 100.0, "telemetry")
            for name in ("slow_voltage_rise", "prolonged_main_duration", "weak_ah_progress", "relaxation_decay", "thermal_without_voltage_gain", "self_discharge_indicator", "low_voltage_persistent")
        ))
        report = BatteryDiagnosticsEngine().evaluate(BatteryDiagnosticEvidence(), bank_fault=bank)
        self.assertEqual(report.authority.authority, DiagnosticAuthority.BLOCK_AUTOMATIC_HV)

    def test_legacy_snapshot_maps_to_signals(self):
        evidence = LegacyBankFaultAdapter.from_snapshot(
            {"reasons": ["main_slow_v_rise<0.8V", "main_duration>20h"]}, timestamp=100.0,
        )
        self.assertTrue(evidence.signal("slow_voltage_rise").value)
        self.assertTrue(evidence.signal("prolonged_main_duration").value)

    def test_safety_evidence_is_read_only_boundary(self):
        evidence = safety_evidence_from_diagnostic(
            BatteryDiagnosticsEngine().evaluate(BatteryDiagnosticEvidence()).authority,
            timestamp=100.0,
        )
        self.assertIsInstance(evidence, SafetyEvidence)
        self.assertTrue(evaluate_safety_evidence(evidence))


if __name__ == "__main__":
    unittest.main()
