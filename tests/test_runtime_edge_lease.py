import types
import unittest

from runtime_safety import RuntimeSafetyError
from runtime_safety_strict import install_strict_runtime_safety


def live_state(**overrides):
    state = {
        "battery_voltage": 14.6,
        "current": 1.0,
        "temp_ext": 25.0,
        "temp_int": 32.0,
        "input_voltage": 64.0,
        "switch": "on",
        "ovp_triggered": "off",
        "ocp_triggered": "off",
        "set_voltage": 14.8,
        "set_current": 2.0,
        "ovp": 14.9,
        "ocp": 2.1,
    }
    state.update(overrides)
    return state


class FakeController:
    def __init__(self):
        self.is_active = True

    def _recipe_envelope(self):
        return types.SimpleNamespace(voltage_ceiling_v=16.5)


class FakeHass:
    def __init__(self, state=None):
        self.live = dict(state or live_state())
        self.turn_on_calls = 0
        self.turn_off_calls = 0

    async def get_all_live(self):
        return dict(self.live)

    async def turn_on(self, entity_id=None):
        self.turn_on_calls += 1
        self.live["switch"] = "on"
        return True

    async def turn_off(self, entity_id=None):
        self.turn_off_calls += 1
        self.live["switch"] = "off"
        return True

    async def set_voltage(self, value):
        self.live["set_voltage"] = float(value)
        return True

    async def set_current(self, value):
        self.live["set_current"] = float(value)
        return True

    async def set_ovp(self, value):
        self.live["ovp"] = float(value)
        return True

    async def set_ocp(self, value):
        self.live["ocp"] = float(value)
        return True


class FakeLease:
    def __init__(self):
        self.arm_calls = 0
        self.renew_calls = 0
        self.disarm_calls = 0
        self.fail_arm = False
        self.fail_renew = False
        self.disarm_result = True

    async def arm(self):
        self.arm_calls += 1
        if self.fail_arm:
            raise RuntimeError("synthetic arm failure")
        return object()

    async def renew_if_due(self):
        self.renew_calls += 1
        if self.fail_renew:
            raise RuntimeError("synthetic renewal failure")
        return object()

    async def disarm(self):
        self.disarm_calls += 1
        return self.disarm_result


class FakeApp:
    def __init__(self, *, state=None):
        self.hass = FakeHass(state)
        self.charge_controller = FakeController()
        self.edge_safety_lease = FakeLease()
        self.notices = []

    def _charge_notify(self, message):
        self.notices.append(message)


class RuntimeEdgeLeaseTests(unittest.IsolatedAsyncioTestCase):
    def _guard(self, app):
        guard = install_strict_runtime_safety(app)
        guard.OFF_CONFIRMATION_WINDOW_S = 0.0
        guard.OFF_CONFIRMATION_POLL_S = 0.0
        return guard

    async def test_output_enable_arms_edge_lease_before_physical_on(self):
        app = FakeApp(state=live_state(switch="off", current=0.0))
        self._guard(app)

        self.assertTrue(await app.hass.turn_on())

        self.assertEqual(app.edge_safety_lease.arm_calls, 1)
        self.assertEqual(app.hass.turn_on_calls, 1)
        self.assertEqual(app.hass.live["switch"], "on")

    async def test_failed_edge_arm_blocks_physical_on(self):
        app = FakeApp(state=live_state(switch="off", current=0.0))
        app.edge_safety_lease.fail_arm = True
        self._guard(app)

        with self.assertRaises(RuntimeSafetyError):
            await app.hass.turn_on()

        self.assertEqual(app.hass.turn_on_calls, 0)
        self.assertEqual(app.hass.live["switch"], "off")

    async def test_lost_lease_while_running_forces_verified_off(self):
        app = FakeApp()
        app.edge_safety_lease.fail_renew = True
        self._guard(app)

        with self.assertRaises(RuntimeSafetyError):
            await app.hass.get_all_live()

        self.assertEqual(app.edge_safety_lease.renew_calls, 1)
        self.assertEqual(app.hass.turn_off_calls, 1)
        self.assertEqual(app.hass.live["switch"], "off")

    async def test_healthy_running_session_checks_lease(self):
        app = FakeApp()
        self._guard(app)

        live = await app.hass.get_all_live()

        self.assertEqual(live["switch"], "on")
        self.assertEqual(app.edge_safety_lease.renew_calls, 1)
        self.assertEqual(app.hass.turn_off_calls, 0)

    async def test_confirmed_normal_off_disarms_edge_lease(self):
        app = FakeApp()
        self._guard(app)

        self.assertTrue(await app.hass.turn_off())

        self.assertEqual(app.hass.live["switch"], "off")
        self.assertEqual(app.edge_safety_lease.disarm_calls, 1)

    async def test_disarm_failure_keeps_safe_off_and_surfaces_warning(self):
        app = FakeApp()
        app.edge_safety_lease.disarm_result = False
        self._guard(app)

        self.assertTrue(await app.hass.turn_off())

        self.assertEqual(app.hass.live["switch"], "off")
        self.assertTrue(app.notices)


if __name__ == "__main__":
    unittest.main()
