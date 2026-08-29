import types
import unittest

from aiogram.enums import ParseMode

from pb_domain import BatteryCondition, ChargeIntent
from safe_output import EnableResult, SafetyViolation
from v2_startup import start_profile_transactional


class FakeMessage:
    def __init__(self):
        self.chat = types.SimpleNamespace(id=123)
        self.from_user = types.SimpleNamespace(id=7)
        self.answers = []

    async def answer(self, text, **kwargs):
        self.answers.append((text, kwargs))


class FakeController:
    STAGE_PREP = "Подготовка"
    STAGE_MAIN = "Main Charge"

    def __init__(self):
        self.is_active = False
        self.current_stage = self.STAGE_MAIN
        self.started = False
        self.stopped = False
        self.context = None

    def configure_recovery_context(self, **kwargs):
        self.context = kwargs

    def start(self, profile, capacity):
        self.started = True
        self.is_active = True
        self.profile = profile
        self.capacity = capacity

    def _prep_target(self, temp):
        return 12.0, 0.7

    def _main_target(self, temp):
        return 14.8, 7.0

    def stop(self, clear_session=True):
        self.stopped = True
        self.is_active = False


class FakeHass:
    def __init__(self, result):
        self.result = result
        self.enable_kwargs = None
        self.turn_off_calls = 0

    async def get_all_live(self):
        return {
            "battery_voltage": 12.6,
            "current": 0.0,
            "temp_ext": 25.0,
            "ah": 0.0,
        }

    async def safe_enable_output(self, **kwargs):
        self.enable_kwargs = kwargs
        return self.result

    async def turn_off(self, entity_id=None):
        self.turn_off_calls += 1
        return True


class FakeApp:
    ParseMode = ParseMode
    OVP_OFFSET = 0.1
    OCP_OFFSET = 0.1
    ENTITY_MAP = {"switch": "switch.rd6018"}

    def __init__(self, result):
        self.charge_controller = FakeController()
        self.hass = FakeHass(result)
        self.user_dashboard = {}
        self.last_checkpoint_time = 0.0
        self.last_chat_id = None
        self.last_user_id = None
        self.time = types.SimpleNamespace(time=lambda: 1000.0)
        self.events = []

    @staticmethod
    def _safe_float(value, default=0.0):
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _cap_current(value):
        return min(12.0, max(0.1, float(value)))

    def log_event(self, *args):
        self.events.append(args)

    async def send_dashboard(self, *args, **kwargs):
        return 1


PENDING = types.SimpleNamespace(
    profile="EFB",
    capacity_ah=70.0,
    intent=ChargeIntent.RECOVERY,
    battery_id="efb-70",
    condition=BatteryCondition.UNKNOWN,
)


class V2StartupTests(unittest.IsolatedAsyncioTestCase):
    async def test_success_uses_recipe_aware_safe_enable_before_success_message(self):
        app = FakeApp(EnableResult(enabled=True))
        message = FakeMessage()

        ok = await start_profile_transactional(app, message, PENDING)

        self.assertTrue(ok)
        self.assertTrue(app.charge_controller.started)
        self.assertFalse(app.charge_controller.stopped)
        self.assertIsNotNone(app.hass.enable_kwargs)
        self.assertAlmostEqual(app.hass.enable_kwargs["voltage_v"], 14.8)
        self.assertAlmostEqual(app.hass.enable_kwargs["current_a"], 7.0)
        self.assertAlmostEqual(app.hass.enable_kwargs["recipe_voltage_ceiling_v"], 16.5)
        self.assertIn("V2 заряд запущен", message.answers[-1][0])

    async def test_failed_enable_rolls_controller_back_and_forces_output_off(self):
        app = FakeApp(
            EnableResult(
                enabled=False,
                violations=frozenset({SafetyViolation.READBACK_MISMATCH}),
                detail="setpoint readback mismatch",
            )
        )
        message = FakeMessage()

        ok = await start_profile_transactional(app, message, PENDING)

        self.assertFalse(ok)
        self.assertTrue(app.charge_controller.stopped)
        self.assertEqual(app.hass.turn_off_calls, 1)
        self.assertIn("запуск отменён", message.answers[-1][0])
        self.assertNotIn("заряд запущен", message.answers[-1][0])

    async def test_missing_external_temperature_never_starts_controller(self):
        app = FakeApp(EnableResult(enabled=True))
        message = FakeMessage()

        async def bad_live():
            return {
                "battery_voltage": 12.6,
                "current": 0.0,
                "temp_ext": "unavailable",
                "ah": 0.0,
            }

        app.hass.get_all_live = bad_live
        ok = await start_profile_transactional(app, message, PENDING)

        self.assertFalse(ok)
        self.assertFalse(app.charge_controller.started)
        self.assertIsNone(app.hass.enable_kwargs)


if __name__ == "__main__":
    unittest.main()
