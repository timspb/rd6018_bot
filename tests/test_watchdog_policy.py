"""Deterministic decision coverage for managed software watchdog policy."""

from __future__ import annotations

import ast
import math
import unittest
from pathlib import Path

from runtime.safety.watchdog_policy import (
    SOFT_WATCHDOG_RETRY_S,
    WatchdogIncidentState,
    WatchdogSnapshot,
    decide_watchdog,
)


def snapshot(
    *,
    now: float = 400.0,
    heartbeat: float = 100.0,
    timeout: float = 180.0,
    suspended: bool = False,
    managed: bool = True,
) -> WatchdogSnapshot:
    return WatchdogSnapshot(now, heartbeat, timeout, suspended, managed)


class WatchdogPolicyTests(unittest.TestCase):
    def test_fresh_heartbeat_below_timeout_resets_incident(self):
        previous = WatchdogIncidentState(True, True, False, 200.0)
        decision = decide_watchdog(
            snapshot(now=279.999, heartbeat=100.0), previous
        )
        self.assertEqual(decision.incident, WatchdogIncidentState())
        self.assertFalse(decision.log_incident)
        self.assertFalse(decision.attempt_shutdown)

    def test_timeout_boundary_is_expired(self):
        decision = decide_watchdog(snapshot(now=280.0, heartbeat=100.0), WatchdogIncidentState())
        self.assertTrue(decision.incident.active)
        self.assertTrue(decision.log_incident)
        self.assertTrue(decision.attempt_shutdown)

    def test_missing_and_future_heartbeat_reset_under_positive_timeout(self):
        for heartbeat in (0.0, -1.0, math.inf, 401.0):
            with self.subTest(heartbeat=heartbeat):
                decision = decide_watchdog(
                    snapshot(now=400.0, heartbeat=heartbeat),
                    WatchdogIncidentState(True, True, False, 350.0),
                )
                self.assertEqual(decision.incident, WatchdogIncidentState())
                self.assertFalse(decision.attempt_shutdown)

    def test_malformed_clock_evidence_preserves_original_comparison_semantics(self):
        cases = (
            (400.0, math.nan, 180.0),
            (400.0, 100.0, math.nan),
            (math.nan, 100.0, 180.0),
            (400.0, 100.0, 0.0),
            (400.0, 100.0, -1.0),
            (math.inf, 100.0, 180.0),
            (400.0, 100.0, -math.inf),
        )
        for now, heartbeat, timeout in cases:
            with self.subTest(now=now, heartbeat=heartbeat, timeout=timeout):
                decision = decide_watchdog(
                    snapshot(now=now, heartbeat=heartbeat, timeout=timeout),
                    WatchdogIncidentState(),
                )
                self.assertTrue(decision.attempt_shutdown)

    def test_idle_timeout_records_incident_without_effects_or_logging(self):
        decision = decide_watchdog(
            snapshot(managed=False), WatchdogIncidentState()
        )
        self.assertTrue(decision.incident.active)
        self.assertFalse(decision.incident.logged)
        self.assertFalse(decision.log_incident)
        self.assertFalse(decision.attempt_shutdown)

    def test_managed_on_timeout_requests_stop_and_one_log(self):
        decision = decide_watchdog(snapshot(managed=True), WatchdogIncidentState())
        self.assertTrue(decision.incident.logged)
        self.assertEqual(decision.incident.last_attempt_at, 400.0)
        self.assertTrue(decision.log_incident)
        self.assertTrue(decision.attempt_shutdown)

    def test_each_revoked_authority_suspends_and_resets_incident(self):
        for reason in ("hands_off", "startup_unresolved", "edge_autonomous", "release"):
            with self.subTest(reason=reason):
                decision = decide_watchdog(
                    snapshot(suspended=True),
                    WatchdogIncidentState(True, True, False, 390.0),
                )
                self.assertEqual(decision.incident, WatchdogIncidentState())
                self.assertFalse(decision.log_incident)
                self.assertFalse(decision.attempt_shutdown)

    def test_retry_is_blocked_before_60_seconds_and_allowed_at_boundary(self):
        previous = WatchdogIncidentState(True, True, False, 400.0)
        blocked = decide_watchdog(
            snapshot(now=400.0 + SOFT_WATCHDOG_RETRY_S - 0.001), previous
        )
        self.assertFalse(blocked.log_incident)
        self.assertFalse(blocked.attempt_shutdown)
        allowed = decide_watchdog(
            snapshot(now=400.0 + SOFT_WATCHDOG_RETRY_S), previous
        )
        self.assertFalse(allowed.log_incident)
        self.assertTrue(allowed.attempt_shutdown)
        self.assertEqual(allowed.incident.last_attempt_at, 460.0)

    def test_successful_shutdown_is_terminal_until_heartbeat_reset(self):
        complete = WatchdogIncidentState(True, True, True, 400.0)
        timed_out = decide_watchdog(snapshot(now=1000.0), complete)
        self.assertFalse(timed_out.log_incident)
        self.assertFalse(timed_out.attempt_shutdown)
        self.assertTrue(timed_out.incident.shutdown_complete)

        reset = decide_watchdog(
            snapshot(now=1000.0, heartbeat=900.0), timed_out.incident
        )
        self.assertEqual(reset.incident, WatchdogIncidentState())

    def test_policy_has_no_runtime_or_effect_dependencies(self):
        root = Path(__file__).resolve().parents[1]
        policy_path = root / "runtime" / "safety" / "watchdog_policy.py"
        adapter_path = root / "runtime" / "safety" / "soft_watchdog.py"
        runtime_path = root / "runtime" / "production_runtime.py"
        policy_source = policy_path.read_text(encoding="utf-8")
        policy_tree = ast.parse(policy_source)
        imported_modules = {
            alias.name
            for node in ast.walk(policy_tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        imported_modules.update(
            node.module
            for node in ast.walk(policy_tree)
            if isinstance(node, ast.ImportFrom)
        )
        self.assertTrue(imported_modules <= {"__future__", "dataclasses", "math"})
        self.assertNotRegex(
            policy_source,
            r"(?i)(log_event|logger|_hard_stop_charge|actuator|hass|transport|physical)",
        )

        adapter_source = adapter_path.read_text(encoding="utf-8")
        self.assertIn("decide_watchdog(", adapter_source)
        self.assertIn("await app._hard_stop_charge()", adapter_source)
        self.assertIn("_log_watchdog_incident(app)", adapter_source)
        runtime_source = runtime_path.read_text(encoding="utf-8")
        self.assertIn(
            "from runtime.safety.soft_watchdog import "
            "SoftWatchdogIncident, soft_watchdog_poll_once",
            runtime_source,
        )
        self.assertIn(
            "await soft_watchdog_poll_once(app, _soft_watchdog_incident)",
            runtime_source,
        )
        self.assertNotIn("decide_watchdog(", runtime_source)


if __name__ == "__main__":
    unittest.main()
