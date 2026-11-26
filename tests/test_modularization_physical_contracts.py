"""Fake-only parity checks for the P3 physical execution contracts."""

from __future__ import annotations

import asyncio
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from application.execution_intent.models import ExecutionIntent, SafetyContext
from application.execution_port import ExecutionPort
from rd6018_telemetry import ProtectionStatus, resolve_protection


def _intent(voltage: float = 14.4, current: float = 2.0) -> ExecutionIntent:
    return ExecutionIntent(
        requested_voltage_v=voltage,
        requested_current_a=current,
        requested_mode="MANUAL_MIX_SETPOINT",
        source_decision_id="p3-1a-test",
        safety_context=SafetyContext(telemetry_state="FRESH", verification_state="REQUIRED"),
    )


class _FakeOwner:
    def __init__(self, switch: str = "on") -> None:
        self.calls: list[tuple] = []
        self.live = {
            "switch": switch,
            "battery_voltage": 12.8,
            "set_voltage_readback_v2": 14.4,
            "set_current_readback_v2": 2.0,
            "_meta": {
                "set_voltage_readback_v2": {"status": "ok", "age_s": 0.0},
                "set_current_readback_v2": {"status": "ok", "age_s": 0.0},
            },
        }

    async def get_all_live(self):
        self.calls.append(("get_all_live",))
        return self.live

    async def set_current(self, value):
        self.calls.append(("set_current", value))
        self.live["set_current_readback_v2"] = value
        return True

    async def set_voltage(self, value):
        self.calls.append(("set_voltage", value))
        self.live["set_voltage_readback_v2"] = value
        return True

    async def turn_on(self):
        self.calls.append(("turn_on",))
        return True

    async def turn_off(self):
        self.calls.append(("turn_off",))
        return True


class ModularizationPhysicalContractTests(unittest.TestCase):
    def test_apply_intent_preconditions_then_current_before_voltage(self):
        owner = _FakeOwner()
        identity = SimpleNamespace(session_id="session", trace_id="trace")
        result = asyncio.run(ExecutionPort(owner).apply_intent(_intent(), identity=identity))
        self.assertTrue(result.verified)
        self.assertEqual(
            [call[0] for call in owner.calls],
            ["get_all_live", "set_current", "set_voltage", "get_all_live"],
        )

    def test_program_voltage_current_keeps_voltage_before_current(self):
        owner = _FakeOwner()
        result = asyncio.run(ExecutionPort(owner).program_voltage_current(14.4, 2.0))
        self.assertEqual(result, (True, True))
        self.assertEqual([call[0] for call in owner.calls], ["set_voltage", "set_current"])

    def test_unavailable_output_or_quarantine_never_issues_on(self):
        owner = _FakeOwner(switch="unavailable")
        result = asyncio.run(
            ExecutionPort(owner).apply_intent(
                _intent(), identity=SimpleNamespace(session_id="session", trace_id="trace")
            )
        )
        self.assertFalse(result.accepted)
        self.assertNotIn("set_current", [call[0] for call in owner.calls])
        self.assertNotIn("set_voltage", [call[0] for call in owner.calls])
        self.assertNotIn("turn_on", [call[0] for call in owner.calls])

        quarantined_owner = _FakeOwner()
        port = ExecutionPort(quarantined_owner)
        port.session_recovery_guard.quarantine("test")
        self.assertFalse(asyncio.run(port.request_verified_on()))
        self.assertNotIn("turn_on", [call[0] for call in quarantined_owner.calls])

    def test_verified_off_evidence_accepts_only_fresh_post_off_sensor_state_off(self):
        class NativeOwner(_FakeOwner):
            def __init__(self, report_factory):
                super().__init__()
                self.report_factory = report_factory

            async def turn_off(self):
                self.calls.append(("turn_off",))
                return True

            async def get_native_physical_output_report(self):
                self.calls.append(("native_report",))
                return self.report_factory()

        def report(value=0.0, *, timestamp=None, age=0.1, native_type="SensorState", status="ok"):
            stamp = time.monotonic() if timestamp is None else timestamp
            return value, {
                "subscription_timestamp_monotonic": stamp,
                "age_s": age,
                "native_type": native_type,
                "status": status,
            }

        accepted_owner = NativeOwner(lambda: report())
        evidence = asyncio.run(ExecutionPort(accepted_owner).request_verified_off_evidence())
        self.assertIsNotNone(evidence)
        self.assertEqual(accepted_owner.calls[0], ("turn_off",))
        self.assertEqual(accepted_owner.calls[1], ("native_report",))
        # The receipt proves native register-18 OFF only; it does not assert measured U/I.

        rejected = (
            lambda: report(timestamp=time.monotonic() - 1.0),  # stale / pre-command
            lambda: None,  # missing report
            lambda: report(native_type="BinarySensorState"),  # wrong callback type
            lambda: report(status="unavailable"),  # wrong status
            lambda: report(value=1.0),  # register-18 ON
        )
        for factory in rejected:
            owner = NativeOwner(factory)
            with patch("application.execution_port.NATIVE_OFF_EVIDENCE_TIMEOUT_S", 0):
                self.assertIsNone(asyncio.run(ExecutionPort(owner).request_verified_off_evidence()))
            self.assertEqual(owner.calls[0], ("turn_off",))

    def test_canonical_protection_codes_keep_opp_separate(self):
        normal = resolve_protection({"protection_code": 0})
        self.assertEqual(normal.status, ProtectionStatus.NORMAL)
        self.assertFalse(normal.tripped)

        ovp = resolve_protection({"protection_code": 1})
        self.assertEqual(ovp.status, ProtectionStatus.OVP)
        self.assertTrue(ovp.tripped)
        self.assertTrue(ovp.ovp)

        ocp = resolve_protection({"protection_code": 2})
        self.assertEqual(ocp.status, ProtectionStatus.OCP)
        self.assertTrue(ocp.tripped)
        self.assertTrue(ocp.ocp)

        opp = resolve_protection({"protection_code": 3})
        self.assertEqual(opp.status, ProtectionStatus.OPP)
        self.assertTrue(opp.tripped)
        self.assertTrue(opp.opp)
        self.assertFalse(opp.ovp or opp.ocp)

        for live in ({}, {"protection_code": "unknown"}, {"protection_code": "unavailable"}):
            state = resolve_protection(live)
            self.assertEqual(state.status, ProtectionStatus.UNKNOWN)
            self.assertTrue(state.tripped)
            self.assertTrue(state.unknown)
            self.assertIsNone(state.code)


if __name__ == "__main__":
    unittest.main()
