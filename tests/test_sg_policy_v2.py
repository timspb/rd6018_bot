import os
import tempfile
import unittest

import database
from battery_diagnostics import DiagnosticHypothesis, DiagnosticLevel
from battery_registry import init_battery_registry, upsert_battery
from pb_domain import BatteryChemistry, BatteryIdentity, BatteryLifecycle
from sg_policy_v2 import (
    HydrometerMode,
    SGAccess,
    SGCorrectionProfile,
    SGMeasurementMetadata,
    SGPromptPoint,
    corrected_specific_gravity,
    decide_sg_prompt,
    get_sg_access,
    get_sg_measurement_metadata,
    record_sg_measurement_metadata,
    set_sg_access,
)


class SpecificGravityCorrectionPolicyTests(unittest.TestCase):
    def test_raw_only_does_not_invent_a_corrected_value(self) -> None:
        value = corrected_specific_gravity(
            1.250,
            temperature_c=35.0,
            hydrometer_mode=HydrometerMode.RAW,
            correction_profile=SGCorrectionProfile.RAW_ONLY,
        )
        self.assertIsNone(value)

    def test_temperature_compensated_hydrometer_is_not_corrected_twice(self) -> None:
        value = corrected_specific_gravity(
            1.267,
            temperature_c=35.0,
            hydrometer_mode=HydrometerMode.TEMPERATURE_COMPENSATED,
            correction_profile=SGCorrectionProfile.RAW_ONLY,
        )
        self.assertAlmostEqual(value or 0.0, 1.267, places=6)

    def test_explicit_trojan_80f_profile(self) -> None:
        value = corrected_specific_gravity(
            1.250,
            temperature_c=32.2222222222,  # 90 F: +0.004 by Trojan maintenance convention
            hydrometer_mode=HydrometerMode.RAW,
            correction_profile=SGCorrectionProfile.TROJAN_80F,
        )
        self.assertAlmostEqual(value or 0.0, 1.254, places=6)

    def test_explicit_rolls_25c_profile(self) -> None:
        value = corrected_specific_gravity(
            1.250,
            temperature_c=35.0,  # +0.003 per 5 C -> +0.006
            hydrometer_mode=HydrometerMode.RAW,
            correction_profile=SGCorrectionProfile.ROLLS_25C,
        )
        self.assertAlmostEqual(value or 0.0, 1.256, places=6)

    def test_named_profile_requires_raw_hydrometer(self) -> None:
        with self.assertRaises(ValueError):
            corrected_specific_gravity(
                1.250,
                temperature_c=25.0,
                hydrometer_mode=HydrometerMode.UNKNOWN,
                correction_profile=SGCorrectionProfile.ROLLS_25C,
            )


class SpecificGravityPromptPolicyTests(unittest.TestCase):
    def test_agm_never_prompts_even_if_access_is_claimed(self) -> None:
        decision = decide_sg_prompt(
            chemistry=BatteryChemistry.AGM,
            access=SGAccess.SERVICEABLE,
            point=SGPromptPoint.DIAGNOSTIC_VERIFY,
            hypothesis=DiagnosticHypothesis.CELL_FAULT,
            level=DiagnosticLevel.HIGH,
        )
        self.assertFalse(decision.should_prompt)
        self.assertEqual(decision.reason, "agm_no_electrolyte_sampling")

    def test_unknown_efb_access_must_be_confirmed_first(self) -> None:
        decision = decide_sg_prompt(
            chemistry=BatteryChemistry.EFB,
            access=SGAccess.UNKNOWN,
            point=SGPromptPoint.DIAGNOSTIC_VERIFY,
            hypothesis=DiagnosticHypothesis.STRATIFICATION,
            level=DiagnosticLevel.VERIFY,
        )
        self.assertFalse(decision.should_prompt)
        self.assertEqual(decision.reason, "electrolyte_access_unconfirmed")

    def test_serviceable_efb_can_prompt_when_sg_resolves_verify_state(self) -> None:
        decision = decide_sg_prompt(
            chemistry=BatteryChemistry.EFB,
            access=SGAccess.SERVICEABLE,
            point=SGPromptPoint.DIAGNOSTIC_VERIFY,
            hypothesis=DiagnosticHypothesis.STRATIFICATION,
            level=DiagnosticLevel.VERIFY,
        )
        self.assertTrue(decision.should_prompt)
        self.assertEqual(decision.reason, "sg_resolves_diagnostic_ambiguity")

    def test_routine_charge_does_not_nag_for_sg(self) -> None:
        decision = decide_sg_prompt(
            chemistry=BatteryChemistry.FLOODED,
            access=SGAccess.SERVICEABLE,
            point=SGPromptPoint.ROUTINE,
        )
        self.assertFalse(decision.should_prompt)
        self.assertEqual(decision.reason, "routine_sg_not_requested")

    def test_prior_imbalance_gets_post_corrective_retest(self) -> None:
        decision = decide_sg_prompt(
            chemistry=BatteryChemistry.CA_CA,
            access=SGAccess.SERVICEABLE,
            point=SGPromptPoint.POST_CORRECTIVE_RETEST,
            prior_imbalance=True,
        )
        self.assertTrue(decision.should_prompt)
        self.assertEqual(decision.reason, "retest_prior_cell_imbalance")

    def test_unsafe_measurement_window_never_prompts(self) -> None:
        decision = decide_sg_prompt(
            chemistry=BatteryChemistry.FLOODED,
            access=SGAccess.SERVICEABLE,
            point=SGPromptPoint.DIAGNOSTIC_VERIFY,
            hypothesis=DiagnosticHypothesis.CELL_FAULT,
            level=DiagnosticLevel.HIGH,
            safe_to_measure=False,
        )
        self.assertFalse(decision.should_prompt)
        self.assertEqual(decision.reason, "measurement_not_safe_now")


class SpecificGravityPolicyStoreTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        await database.close_db()
        self.tempdir = tempfile.TemporaryDirectory()
        self.old_db_path = database.DB_PATH
        database.DB_PATH = os.path.join(self.tempdir.name, "test.db")
        await init_battery_registry()
        self.identity = BatteryIdentity("efb-serviceable", BatteryChemistry.EFB, 70)
        await upsert_battery(self.identity, BatteryLifecycle(), updated_at=1.0)

    async def asyncTearDown(self) -> None:
        await database.close_db()
        database.DB_PATH = self.old_db_path
        self.tempdir.cleanup()

    async def test_access_round_trip_is_bound_to_physical_battery(self) -> None:
        self.assertEqual(await get_sg_access(self.identity.battery_id), SGAccess.UNKNOWN)
        await set_sg_access(self.identity.battery_id, SGAccess.SERVICEABLE, updated_at=10.0)
        self.assertEqual(await get_sg_access(self.identity.battery_id), SGAccess.SERVICEABLE)

    async def test_measurement_policy_round_trip(self) -> None:
        metadata = SGMeasurementMetadata(
            battery_id=self.identity.battery_id,
            measured_at=100.0,
            hydrometer_mode=HydrometerMode.RAW,
            correction_profile=SGCorrectionProfile.ROLLS_25C,
        )
        await record_sg_measurement_metadata(metadata)
        stored = await get_sg_measurement_metadata(self.identity.battery_id, 100.0)
        self.assertEqual(stored, metadata)

    async def test_double_correction_policy_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            await record_sg_measurement_metadata(
                SGMeasurementMetadata(
                    battery_id=self.identity.battery_id,
                    measured_at=101.0,
                    hydrometer_mode=HydrometerMode.TEMPERATURE_COMPENSATED,
                    correction_profile=SGCorrectionProfile.TROJAN_80F,
                )
            )


if __name__ == "__main__":
    unittest.main()
