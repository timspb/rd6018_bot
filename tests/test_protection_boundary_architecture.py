from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]

DISALLOWED = (
    "application/main_guard_transaction.py",
    "application/main_guard_runtime.py",
    "application/operator_snapshot_provider.py",
    "runtime/charge/strategy/main_guard_admission.py",
    "runtime/charge/strategy/main_guard_pre_on.py",
    "runtime/charge/session.py",
    "rd_managed_adoption.py",
    "operator_hmi.py",
    "runtime/ui/components/hmi_live_safety.py",
    "runtime/ui/components/hmi_service_details.py",
    "runtime/production_runtime.py",
)

RAW_PROTECTION_TOKENS = (
    "protection_code",
    "ovp_triggered",
    "ocp_triggered",
    "decode_protection_code",
    "resolve_protection",
    "ProtectionStatus",
)


class ProtectionBoundaryArchitectureTests(unittest.TestCase):
    def test_program_application_session_and_ui_do_not_decode_raw_protection(self):
        leaks = {}
        for relative in DISALLOWED:
            source = (ROOT / relative).read_text(encoding="utf-8")
            found = [token for token in RAW_PROTECTION_TOKENS if token in source]
            if found:
                leaks[relative] = found
        self.assertEqual(leaks, {})

    def test_raw_protection_decoder_is_confined_to_telemetry_safety_boundary(self):
        source = (ROOT / "runtime/safety/protection_boundary.py").read_text(encoding="utf-8")
        self.assertIn("decode_protection_code", source)
        self.assertIn("ProtectionVerdict", source)
        self.assertIn("native_protection_generation", source)

    def test_main_guard_consumes_generic_safety_projection(self):
        for relative in (
            "application/main_guard_transaction.py",
            "runtime/charge/strategy/main_guard_admission.py",
            "runtime/charge/strategy/main_guard_pre_on.py",
        ):
            source = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn("assess_protection", source)
            self.assertIn("ProtectionVerdict", source)

    def test_edge_orchestrators_do_not_bypass_lease_transport_boundary(self):
        forbidden = (
            ".hass",
            "get_state",
            "get_button_info",
            "press_button",
            "decode_protection_code",
            "resolve_protection",
            "ProtectionStatus",
            "register-16",
        )
        for relative in ("edge_live_adoption.py", "edge_autonomous_mode.py"):
            source = (ROOT / relative).read_text(encoding="utf-8")
            leaks = [token for token in forbidden if token in source]
            self.assertEqual(leaks, [], relative)

    def test_edge_live_adoption_consumes_generic_protection_verdict(self):
        source = (ROOT / "edge_live_adoption.py").read_text(encoding="utf-8")
        self.assertIn("read_protection_assessment", source)
        self.assertIn("ProtectionVerdict", source)
        self.assertNotIn("protection_code", source)


if __name__ == "__main__":
    unittest.main()
