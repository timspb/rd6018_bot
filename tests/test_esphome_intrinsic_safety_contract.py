from pathlib import Path
import unittest


class EspHomeIntrinsicSafetyContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package = Path(
            "esphome/packages/rd6018_intrinsic_safety.yaml"
        ).read_text(encoding="utf-8")
        cls.target = Path("esphome/rd6018.yaml").read_text(encoding="utf-8")
        cls.executable_package = "\n".join(
            line.split("#", 1)[0] for line in cls.package.splitlines()
        )

    def test_canonical_target_includes_intrinsic_safety_package(self):
        self.assertIn(
            "intrinsic_safety: !include packages/rd6018_intrinsic_safety.yaml",
            self.target,
        )

    def test_existing_internal_psu_cutoff_is_enforced_locally(self):
        self.assertIn('rd6018_intrinsic_temp_cutoff_c: "55.0"', self.package)
        self.assertIn("id(rd6018_temperature_internal_v2).state", self.package)
        self.assertIn(
            "temp_int >= ${rd6018_intrinsic_temp_cutoff_c}f",
            self.package,
        )
        self.assertIn("switch.turn_off: rd6018_safety_output", self.package)

    def test_raw_rd_protection_status_is_local_off_authority(self):
        self.assertIn("id(rd6018_protection_status_code).state", self.package)
        self.assertIn("((uint16_t) protection) != 0U", self.package)
        self.assertIn("switch.turn_off: rd6018_safety_output", self.package)

    def test_intrinsic_guard_is_not_pb_or_control_plane_gated(self):
        executable = self.executable_package.lower()
        for forbidden in (
            "temp_ext",
            "battery_voltage",
            "charge_session",
            "controller_active",
            "rd6018_safety_managed_session",
            "rd6018_safety_last_renew_ms",
            "wifi",
            "homeassistant",
            "telegram",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, executable)

    def test_missing_telemetry_is_not_converted_into_an_autonomous_off_reason(self):
        # Positive evidence only: NaN/unknown temperature or protection state does
        # not satisfy the intrinsic-fault predicate. Managed telemetry-loss policy
        # remains separately owned by the lease/runtime layers.
        self.assertIn("!isnan(temp_int)", self.package)
        self.assertIn("!isnan(protection)", self.package)
        self.assertNotIn("isnan(temp_int) ||", self.package)
        self.assertNotIn("isnan(protection) ||", self.package)

    def test_intrinsic_guard_never_reprograms_generic_psu_setpoints(self):
        for actuator in (
            "set_voltage",
            "set_current",
            "set_ovp",
            "set_ocp",
            "create_write_single_command",
            "switch.turn_on",
        ):
            with self.subTest(actuator=actuator):
                self.assertNotIn(actuator, self.executable_package)


if __name__ == "__main__":
    unittest.main()
