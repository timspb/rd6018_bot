import ast
import pathlib
import unittest

from runtime.charge import BatteryProfile, ChargeLimits, ChemistryProfile


class V3BatteryDomainTests(unittest.TestCase):
    def setUp(self):
        self.limits = ChargeLimits(
            max_voltage=15.0,
            absorption_voltage=14.4,
            float_voltage=13.8,
            max_current=8.0,
            temperature_compensation_mv_per_c=-3.0,
            compensation_reference_c=25.0,
        )

    def test_creates_supported_chemistry_profiles(self):
        profiles = [
            BatteryProfile(ChemistryProfile.AGM, 80.0, "Varta", limits=self.limits),
            BatteryProfile(ChemistryProfile.EFB, 72.0, "BaiCal", limits=self.limits),
            BatteryProfile(ChemistryProfile.CALCIUM, 80.0, limits=self.limits),
        ]

        self.assertEqual(
            [ChemistryProfile.AGM, ChemistryProfile.EFB, ChemistryProfile.CALCIUM],
            [profile.chemistry for profile in profiles],
        )

    def test_limits_validate_order_and_positive_values(self):
        with self.assertRaises(ValueError):
            ChargeLimits(14.0, 14.4, 13.8, 8.0)
        with self.assertRaises(ValueError):
            ChargeLimits(15.0, 14.4, 13.8, 0.0)
        with self.assertRaises(ValueError):
            ChargeLimits(15.0, 14.4, 13.8, 8.0, temperature_compensation_mv_per_c=-3.0)

    def test_battery_profile_rejects_invalid_identity(self):
        with self.assertRaises(ValueError):
            BatteryProfile(ChemistryProfile.AGM, 0.0, limits=self.limits)
        with self.assertRaises(TypeError):
            BatteryProfile("AGM", 80.0, limits=self.limits)

    def test_domain_has_no_external_dependencies_or_program_classes(self):
        root = pathlib.Path(__file__).parents[1] / "runtime" / "charge"
        forbidden = {"bot_legacy", "hass_api", "aiogram", "rd_control_mode", "safe_output"}
        for path in (root / "battery.py", root / "chemistry.py", root / "limits.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    self.assertTrue(forbidden.isdisjoint({a.name.split(".")[0] for a in node.names}))
                elif isinstance(node, ast.ImportFrom):
                    self.assertNotIn((node.module or "").split(".")[0], forbidden)
        self.assertFalse(any(name in dir(__import__("runtime.charge", fromlist=["x"])) for name in ("AGMProgram", "EFBProgram", "CalciumProgram")))


if __name__ == "__main__":
    unittest.main()
