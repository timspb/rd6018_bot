import unittest
from types import SimpleNamespace

from soft_watchdog_containment import (
    SOFT_WATCHDOG_RETRY_S,
    SoftWatchdogIncident,
    soft_watchdog_poll_once,
)


class DummyLogger:
    def __init__(self):
        self.critical_messages = []
        self.error_messages = []

    def critical(self, message, *args):
        self.critical_messages.append(message % args if args else message)

    def error(self, message, *args):
        self.error_messages.append(message % args if args else message)


class DummyApp:
    SOFT_WATCHDOG_TIMEOUT = 180.0

    def __init__(
        self,
        *,
        output_on=False,
        controller_active=False,
        manual_active=False,
        hands_off=False,
        edge_autonomous=False,
        release_in_progress=False,
        startup_ready=True,
    ):
        self.last_ha_ok_time = 100.0
        self.charge_controller = SimpleNamespace(
            _last_known_output_on=bool(output_on),
            is_active=bool(controller_active),
            current_stage="Main Charge" if controller_active else "Idle",
        )
        self.manual_session_manager = SimpleNamespace(is_active=bool(manual_active))
        self.rd_control_mode_manager = SimpleNamespace(
            hands_off=bool(hands_off),
            edge_autonomous=bool(edge_autonomous),
            release_in_progress=bool(release_in_progress),
        )
        self.rd_startup_authority_gate = SimpleNamespace(
            managed_actuation_ready=bool(startup_ready)
        )
        self.runtime_safety_guard = None
        self.logger = DummyLogger()
        self.hard_stop_calls = 0
        self.fail_hard_stop = False
        self.events = []

    def log_event(self, *args):
        self.events.append(args)

    async def _hard_stop_charge(self):
        self.hard_stop_calls += 1
        if self.fail_hard_stop:
            raise RuntimeError("synthetic remote I/O failure")


class SoftWatchdogContainmentTests(unittest.IsolatedAsyncioTestCase):
    async def test_idle_last_known_off_outage_is_passive(self):
        app = DummyApp(output_on=False, controller_active=False)
        incident = SoftWatchdogIncident()

        await soft_watchdog_poll_once(app, incident, now=400.0)
        await soft_watchdog_poll_once(app, incident, now=500.0)

        self.assertTrue(incident.active)
        self.assertFalse(incident.logged)
        self.assertEqual(app.hard_stop_calls, 0)
        self.assertEqual(app.events, [])
        self.assertEqual(app.logger.critical_messages, [])

    async def test_last_known_on_requests_immediate_stop_and_logs_once(self):
        app = DummyApp(output_on=True)
        incident = SoftWatchdogIncident()

        await soft_watchdog_poll_once(app, incident, now=400.0)
        await soft_watchdog_poll_once(app, incident, now=500.0)

        self.assertEqual(app.hard_stop_calls, 1)
        self.assertTrue(incident.shutdown_complete)
        self.assertEqual(len(app.events), 1)
        self.assertEqual(len(app.logger.critical_messages), 1)

    async def test_failed_remote_stop_retries_only_at_bounded_cadence(self):
        app = DummyApp(output_on=True)
        app.fail_hard_stop = True
        incident = SoftWatchdogIncident()

        await soft_watchdog_poll_once(app, incident, now=400.0)
        await soft_watchdog_poll_once(app, incident, now=410.0)
        await soft_watchdog_poll_once(
            app,
            incident,
            now=400.0 + SOFT_WATCHDOG_RETRY_S - 0.1,
        )
        self.assertEqual(app.hard_stop_calls, 1)

        await soft_watchdog_poll_once(
            app,
            incident,
            now=400.0 + SOFT_WATCHDOG_RETRY_S,
        )
        self.assertEqual(app.hard_stop_calls, 2)
        self.assertEqual(len(app.events), 1)
        self.assertEqual(len(app.logger.critical_messages), 1)

        app.fail_hard_stop = False
        await soft_watchdog_poll_once(
            app,
            incident,
            now=400.0 + 2 * SOFT_WATCHDOG_RETRY_S,
        )
        self.assertEqual(app.hard_stop_calls, 3)
        self.assertTrue(incident.shutdown_complete)

        await soft_watchdog_poll_once(
            app,
            incident,
            now=400.0 + 4 * SOFT_WATCHDOG_RETRY_S,
        )
        self.assertEqual(app.hard_stop_calls, 3)

    async def test_active_controller_is_safety_relevant_even_before_known_output_on(self):
        app = DummyApp(output_on=False, controller_active=True)
        incident = SoftWatchdogIncident()

        await soft_watchdog_poll_once(app, incident, now=400.0)

        self.assertEqual(app.hard_stop_calls, 1)
        self.assertTrue(incident.shutdown_complete)

    async def test_active_manual_session_is_safety_relevant(self):
        app = DummyApp(output_on=False, controller_active=False, manual_active=True)
        incident = SoftWatchdogIncident()

        await soft_watchdog_poll_once(app, incident, now=400.0)

        self.assertEqual(app.hard_stop_calls, 1)
        self.assertTrue(incident.shutdown_complete)

    async def test_hands_off_outage_never_invokes_pb_hard_stop(self):
        app = DummyApp(
            output_on=True,
            controller_active=False,
            hands_off=True,
        )
        incident = SoftWatchdogIncident(
            active=True,
            logged=True,
            shutdown_complete=False,
            last_attempt_at=390.0,
        )

        await soft_watchdog_poll_once(app, incident, now=400.0)
        await soft_watchdog_poll_once(app, incident, now=700.0)

        self.assertEqual(app.hard_stop_calls, 0)
        self.assertFalse(incident.active)
        self.assertFalse(incident.logged)
        self.assertFalse(incident.shutdown_complete)
        self.assertEqual(incident.last_attempt_at, 0.0)
        self.assertEqual(app.events, [])
        self.assertEqual(app.logger.critical_messages, [])

    async def test_autonomous_outage_never_invokes_pb_hard_stop_even_if_software_mode_is_managed(self):
        app = DummyApp(
            output_on=True,
            controller_active=True,
            hands_off=False,
            edge_autonomous=True,
            startup_ready=False,
        )
        incident = SoftWatchdogIncident(active=True, logged=True, last_attempt_at=390.0)

        await soft_watchdog_poll_once(app, incident, now=400.0)
        await soft_watchdog_poll_once(app, incident, now=700.0)

        self.assertEqual(app.hard_stop_calls, 0)
        self.assertFalse(incident.active)
        self.assertEqual(app.events, [])

    async def test_unresolved_startup_authority_never_invokes_pb_hard_stop(self):
        app = DummyApp(
            output_on=True,
            controller_active=True,
            startup_ready=False,
        )
        incident = SoftWatchdogIncident()

        await soft_watchdog_poll_once(app, incident, now=400.0)

        self.assertEqual(app.hard_stop_calls, 0)
        self.assertFalse(incident.active)
        self.assertEqual(app.events, [])

    async def test_live_hands_off_release_suspends_watchdog_during_transfer(self):
        app = DummyApp(
            output_on=True,
            controller_active=True,
            release_in_progress=True,
        )
        incident = SoftWatchdogIncident()

        await soft_watchdog_poll_once(app, incident, now=400.0)

        self.assertEqual(app.hard_stop_calls, 0)
        self.assertFalse(incident.active)
        self.assertEqual(app.events, [])
        self.assertEqual(app.logger.critical_messages, [])

    async def test_fresh_heartbeat_resets_incident_for_future_independent_outage(self):
        app = DummyApp(output_on=True)
        incident = SoftWatchdogIncident()
        app.fail_hard_stop = True

        await soft_watchdog_poll_once(app, incident, now=400.0)
        self.assertTrue(incident.active)
        self.assertEqual(app.hard_stop_calls, 1)

        app.last_ha_ok_time = 390.0
        await soft_watchdog_poll_once(app, incident, now=400.0)
        self.assertFalse(incident.active)
        self.assertFalse(incident.logged)
        self.assertEqual(incident.last_attempt_at, 0.0)

        app.last_ha_ok_time = 100.0
        await soft_watchdog_poll_once(app, incident, now=700.0)
        self.assertEqual(app.hard_stop_calls, 2)
        self.assertEqual(len(app.events), 2)
        self.assertEqual(len(app.logger.critical_messages), 2)


if __name__ == "__main__":
    unittest.main()
