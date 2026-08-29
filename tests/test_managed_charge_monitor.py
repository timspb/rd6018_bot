import unittest
from datetime import datetime, timedelta

from v2_bootstrap import (
    _install_managed_charge_monitor_guard,
    _managed_aware_charge_monitor_poll,
)


class FakeHass:
    def __init__(self, *, voltage=14.71, current=0.09, switch="on"):
        self.live = {
            "battery_voltage": voltage,
            "current": current,
            "switch": switch,
        }

    async def get_all_live(self):
        return dict(self.live)


class FakeLogger:
    def __init__(self):
        self.records = []

    def info(self, *args):
        self.records.append(("info", args))

    def error(self, *args):
        self.records.append(("error", args))


class FakeApp:
    ZERO_CURRENT_THRESHOLD_MINUTES = 30
    CHARGE_ALERT_COOLDOWN = timedelta(hours=1)
    STORAGE_ALERT_COOLDOWN = timedelta(hours=1)
    IDLE_ALERT_COOLDOWN = timedelta(hours=1)

    def __init__(self, *, active=True, voltage=14.71, current=0.09, switch="on"):
        self.hass = FakeHass(voltage=voltage, current=current, switch=switch)
        self.charge_controller = type("Controller", (), {"is_active": active})()
        self.zero_current_since = None
        self.last_charge_alert_at = None
        self.last_idle_alert_at = None
        self.logger = FakeLogger()
        self.notifications = []

        async def old_monitor():
            return None

        self.charge_monitor = old_monitor

    @staticmethod
    def _safe_float(value, default=0.0):
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _charge_notify(self, message):
        self.notifications.append(message)


class ManagedChargeMonitorTests(unittest.IsolatedAsyncioTestCase):
    async def test_managed_cv_tail_does_not_emit_legacy_charge_complete_alert(self):
        app = FakeApp(active=True, voltage=14.71, current=0.09)

        await _managed_aware_charge_monitor_poll(app)

        self.assertEqual(app.notifications, [])
        self.assertIsNone(app.last_charge_alert_at)

    async def test_unmanaged_output_keeps_legacy_low_current_hint(self):
        app = FakeApp(active=False, voltage=14.71, current=0.09)

        await _managed_aware_charge_monitor_poll(app)

        self.assertEqual(len(app.notifications), 1)
        self.assertIn("Заряд завершён или аккумулятор почти полон", app.notifications[0])
        self.assertIn("0.09А", app.notifications[0])
        self.assertIsNotNone(app.last_charge_alert_at)

    async def test_managed_zero_current_does_not_emit_legacy_idle_reminder(self):
        app = FakeApp(active=True, voltage=14.71, current=0.0)
        app.zero_current_since = datetime.now() - timedelta(hours=1)

        await _managed_aware_charge_monitor_poll(app)

        self.assertEqual(app.notifications, [])
        self.assertIsNone(app.zero_current_since)
        self.assertIsNone(app.last_idle_alert_at)

    async def test_output_off_clears_zero_current_clock(self):
        app = FakeApp(active=False, voltage=14.71, current=0.0, switch="off")
        app.zero_current_since = datetime.now() - timedelta(hours=1)

        await _managed_aware_charge_monitor_poll(app)

        self.assertEqual(app.notifications, [])
        self.assertIsNone(app.zero_current_since)

    async def test_guard_replaces_scheduled_legacy_monitor_idempotently(self):
        app = FakeApp(active=True)
        original = app.charge_monitor

        _install_managed_charge_monitor_guard(app)
        guarded = app.charge_monitor
        _install_managed_charge_monitor_guard(app)

        self.assertIsNot(guarded, original)
        self.assertIs(app.charge_monitor, guarded)
        self.assertTrue(app._v2_managed_charge_monitor_guard_installed)


if __name__ == "__main__":
    unittest.main()
