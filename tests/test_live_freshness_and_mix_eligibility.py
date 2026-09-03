import asyncio
import pathlib
import types
import unittest

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from config import ENTITY_MAP
from live_output_readback_v2 import (
    install_output_state_readback,
    promote_output_state_readback,
)
from operator_mix_eligibility import (
    POTENTIAL_MIX_MIN_SETPOINT_V,
    filter_non_mix_actions,
    potential_mix_setpoint,
)


class LiveOutputReadbackV2Tests(unittest.TestCase):
    def test_deployed_output_state_entity_id_is_exact(self):
        self.assertEqual(
            ENTITY_MAP["output_state_code_v2"],
            "sensor.rd6018_rd_6018_output_state_code_v2",
        )

    def test_read_only_output_code_owns_canonical_value_and_freshness(self):
        live = {
            "switch": "on",
            "output_state_code_v2": 0,
            "_meta": {
                "switch": {"status": "ok", "last_reported": "old"},
                "output_state_code_v2": {
                    "status": "ok",
                    "last_reported": "fresh",
                    "last_updated": "fresh",
                },
            },
        }

        promoted = promote_output_state_readback(live)

        self.assertEqual(promoted["switch"], "off")
        self.assertEqual(promoted["_meta"]["switch"]["last_reported"], "fresh")
        self.assertEqual(
            promoted["_meta"]["switch"]["source_key"],
            "output_state_code_v2",
        )

    def test_invalid_output_code_never_overrides_public_switch(self):
        live = {"switch": "on", "output_state_code_v2": 2, "_meta": {}}
        promoted = promote_output_state_readback(live)
        self.assertEqual(promoted["switch"], "on")

    def test_existing_runtime_guard_raw_reader_is_promoted_for_hands_off(self):
        class FakeHass:
            async def get_all_live(self):
                return {
                    "switch": "off",
                    "output_state_code_v2": 1,
                    "_meta": {
                        "switch": {
                            "status": "ok",
                            "last_reported": "stale-public-switch",
                        },
                        "output_state_code_v2": {
                            "status": "ok",
                            "last_reported": "fresh-register-18",
                            "last_updated": "fresh-register-18",
                        },
                    },
                }

        hass = FakeHass()

        class FakeGuard:
            def __init__(self):
                # RuntimeSafetyGuard captures the HA reader before the later
                # HANDS_OFF ownership wrapper starts using _raw_live().
                self._raw_get_all_live = hass.get_all_live

            async def _raw_live(self):
                return await self._raw_get_all_live()

        guard = FakeGuard()
        app = types.SimpleNamespace(hass=hass, runtime_safety_guard=guard)

        install_output_state_readback(app)
        raw = asyncio.run(guard._raw_live())

        self.assertEqual(raw["switch"], "on")
        self.assertEqual(raw["_meta"]["switch"]["last_reported"], "fresh-register-18")
        self.assertEqual(
            raw["_meta"]["switch"]["source_key"],
            "output_state_code_v2",
        )
        self.assertTrue(getattr(guard, "_v2_output_state_readback_raw_installed", False))


class MixActionEligibilityTests(unittest.TestCase):
    def test_low_voltage_hands_off_program_is_not_potential_mix(self):
        self.assertFalse(potential_mix_setpoint(13.60))
        self.assertFalse(potential_mix_setpoint(POTENTIAL_MIX_MIN_SETPOINT_V))
        self.assertTrue(potential_mix_setpoint(POTENTIAL_MIX_MIN_SETPOINT_V + 0.01))

    def test_filter_removes_only_mix_entry_actions(self):
        markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="observer", callback_data="rd_live_mix")],
                [InlineKeyboardButton(text="managed", callback_data="rd_managed_mix")],
                [InlineKeyboardButton(text="Pb", callback_data="rd_managed_adopt")],
                [InlineKeyboardButton(text="OFF", callback_data="rd_hands_off_output_off")],
            ]
        )

        filtered = filter_non_mix_actions(markup)
        callbacks = [
            button.callback_data
            for row in filtered.inline_keyboard
            for button in row
            if button.callback_data
        ]
        self.assertNotIn("rd_live_mix", callbacks)
        self.assertNotIn("rd_managed_mix", callbacks)
        self.assertIn("rd_managed_adopt", callbacks)
        self.assertIn("rd_hands_off_output_off", callbacks)


class ESPHomeSourceHeartbeatContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.node = pathlib.Path("esphome/rd6018.yaml").read_text(encoding="utf-8")
        cls.telemetry = pathlib.Path(
            "esphome/packages/rd6018_telemetry_v2.yaml"
        ).read_text(encoding="utf-8")

    @staticmethod
    def _block(text: str, name: str) -> str:
        return text.split(f'name: "{name}"', 1)[1].split("- platform:", 1)[0]

    def test_stable_critical_numeric_sources_force_ha_reports(self):
        for name in ("Output voltage", "Output current", "Battery voltage"):
            with self.subTest(name=name):
                self.assertIn("force_update: true", self._block(self.node, name))

        for name in (
            "Temperature Internal V2",
            "Temperature External V2",
            "Protection Status Code",
            "Regulation Mode Code",
        ):
            with self.subTest(name=name):
                self.assertIn("force_update: true", self._block(self.telemetry, name))

    def test_output_has_force_updated_read_only_register_18_source(self):
        block = self._block(self.telemetry, "Output State Code V2")
        self.assertIn("address: 18", block)
        self.assertIn("value_type: U_WORD", block)
        self.assertIn("force_update: true", block)


if __name__ == "__main__":
    unittest.main()
