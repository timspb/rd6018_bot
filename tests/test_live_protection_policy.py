"""Live software protection trip policy contracts."""
from __future__ import annotations

import ast
import asyncio
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

from runtime.safety.live_protection import evaluate_live_protection


def live(**overrides):
    data = {"protection_code": 0}
    data.update(overrides)
    return data


class LiveProtectionPolicyTests(unittest.TestCase):
    def test_precritical_internal_temperature_trips_with_output_or_charge(self):
        for state in ((True, False), (False, True)):
            result = evaluate_live_protection(
                live=live(),
                charge_active=state[0], output_on=state[1],
                internal_temperature_c=60.0, precritical_temperature_c=60.0,
            )
            self.assertEqual(result.triggers, ("TEMP_INT_PRECRITICAL",))
            self.assertTrue(result.shutdown_required)

    def test_temperature_below_threshold_and_inactive_output_is_clear(self):
        result = evaluate_live_protection(
            live=live(),
            charge_active=False, output_on=False,
            internal_temperature_c=59.9, precritical_temperature_c=60.0,
        )
        self.assertEqual(result.triggers, ())
        self.assertFalse(result.shutdown_required)

    def test_missing_temperature_does_not_invent_a_trip(self):
        result = evaluate_live_protection(
            live=live(),
            charge_active=True, output_on=True,
            internal_temperature_c=None, precritical_temperature_c=60.0,
        )
        self.assertEqual(result.triggers, ())
        self.assertEqual(result.evidence, ())

    def test_raw_protection_decoding_stays_inside_safety(self):
        source = Path("runtime/safety/live_protection.py").read_text(encoding="utf-8")
        self.assertIn("resolve_protection(live)", source)
        module = ast.parse(source)
        params = {
            arg.arg
            for node in ast.walk(module)
            if isinstance(node, ast.FunctionDef)
            for arg in node.args.kwonlyargs
        }
        self.assertIn("live", params)
        self.assertNotIn("ovp_triggered", params)
        self.assertNotIn("ocp_triggered", params)

    def test_application_dispatch_uses_existing_policy_and_runtime_effect_context(self):
        policy = Path("runtime/safety/live_protection.py").read_text(encoding="utf-8")
        use_case = Path("application/live_protection_use_case.py").read_text(encoding="utf-8")
        runtime = Path("runtime/production_runtime.py").read_text(encoding="utf-8")
        self.assertIn("resolve_protection(live)", policy)
        self.assertIn("decision = evaluate_live_protection(", use_case)
        self.assertEqual(use_case.count("evaluate_live_protection("), 1)
        self.assertIn('"OPP_TRIGGERED" in decision.triggers', use_case)
        self.assertIn('"TEMP_INT_PRECRITICAL" in decision.triggers', use_case)
        self.assertNotIn('"OVP_TRIGGERED" in decision.triggers', use_case)
        self.assertNotIn('"OCP_TRIGGERED" in decision.triggers', use_case)
        self.assertIn("await app._hard_stop_charge()", use_case)
        self.assertIn("await dispatch_live_protection(", runtime)
        self.assertIn("app=sys.modules[__name__]", runtime)

    def test_dispatch_preserves_exact_effect_order_for_opp_temperature_both_and_failure(self):
        from application.live_protection_use_case import dispatch_live_protection

        async def run_case(code, temp, *, stop_error=None):
            events = []
            controller = SimpleNamespace(current_stage="MAIN")
            async def stop():
                events.append("stop")
                controller.current_stage = "Idle"
                if stop_error is not None:
                    raise stop_error
            app = SimpleNamespace(
                charge_controller=controller,
                log_event=lambda *args: events.append(("log", args)),
                _charge_notify=lambda message: events.append(("notify", message)),
                _hard_stop_charge=stop,
            )
            await dispatch_live_protection(
                app=app, live={"protection_code": code}, charge_active=True,
                output_on=True, internal_temperature_c=temp,
                battery_voltage_v=14.2, current_a=3.1,
                external_temperature_c=25.0, amp_hours=12.0,
            )
            return events

        opp_events = asyncio.run(run_case(3, 40.0))
        self.assertEqual([event[0] if isinstance(event, tuple) else event for event in opp_events],
                         ["log", "notify", "stop"])
        self.assertEqual(opp_events[0][1],
                         ("MAIN", 14.2, 3.1, 25.0, 12.0, "OPP_TRIGGERED"))
        self.assertEqual(opp_events[1][1], "🛑 Сработала аппаратная защита мощности. Выход выключен.")

        temp_events = asyncio.run(run_case(0, 60.0))
        self.assertEqual([event[0] if isinstance(event, tuple) else event for event in temp_events],
                         ["log", "notify", "stop"])
        self.assertEqual(temp_events[0][1],
                         ("MAIN", 14.2, 3.1, 25.0, 12.0, "TEMP_INT_PRECRITICAL_60C"))
        self.assertEqual(temp_events[1][1], "🌡 Температура блока 60°C ≥ 55°C. Выход выключен для защиты БП.")

        both_events = asyncio.run(run_case(3, 60.0))
        self.assertEqual([event[0] if isinstance(event, tuple) else event for event in both_events],
                         ["log", "notify", "stop", "log", "notify", "stop"])
        log_args = [event[1] for event in both_events
                    if isinstance(event, tuple) and event[0] == "log"]
        self.assertEqual([args[-1] for args in log_args],
                         ["OPP_TRIGGERED", "TEMP_INT_PRECRITICAL_60C"])
        self.assertEqual([args[1:] for args in log_args],
                         [(14.2, 3.1, 25.0, 12.0, "OPP_TRIGGERED"),
                          (14.2, 3.1, 25.0, 12.0, "TEMP_INT_PRECRITICAL_60C")])
        self.assertEqual([event[1][0] for event in both_events
                          if isinstance(event, tuple) and event[0] == "log"],
                         ["MAIN", "Idle"])

        async def failing_case():
            events = []
            controller = SimpleNamespace(current_stage="MAIN")
            app = SimpleNamespace(
                charge_controller=controller,
                log_event=lambda *args: events.append(("log", args)),
                _charge_notify=lambda message: events.append(("notify", message)),
                _hard_stop_charge=AsyncMock(side_effect=RuntimeError("uncertain OFF")),
            )
            with self.assertRaisesRegex(RuntimeError, "uncertain OFF"):
                await dispatch_live_protection(
                    app=app, live={"protection_code": 3}, charge_active=True,
                    output_on=True, internal_temperature_c=40.0,
                    battery_voltage_v=14.2, current_a=3.1,
                    external_temperature_c=25.0, amp_hours=12.0,
                )
            app._hard_stop_charge.assert_awaited_once()
            self.assertEqual([event[0] for event in events], ["log", "notify"])

        asyncio.run(failing_case())

    def test_inactive_managed_charge_does_not_generate_hardware_trip_dispatch(self):
        for code in (1, 2, 3):
            with self.subTest(code=code):
                result = evaluate_live_protection(
                    live=live(protection_code=code),
                    charge_active=False, output_on=True,
                    internal_temperature_c=40.0, precritical_temperature_c=60.0,
                )
                self.assertEqual(result.triggers, ())

    def test_ovp_ocp_are_observed_but_not_software_trips_while_opp_is(self):
        for code in (1, 2, 3):
            with self.subTest(code=code):
                result = evaluate_live_protection(
                    live=live(protection_code=code),
                    charge_active=True, output_on=True,
                    internal_temperature_c=40.0, precritical_temperature_c=60.0,
                )
                self.assertEqual(result.triggers, ("OPP_TRIGGERED",) if code == 3 else ())
                self.assertEqual(result.shutdown_required, code == 3)


if __name__ == "__main__":
    unittest.main()
