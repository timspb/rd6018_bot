"""D118 regressions for the deferred HassClient START bypass and callback ACK."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
import unittest
from datetime import datetime, timezone

from runtime.safety.edge_lease import EdgeSafetyLease, EdgeSafetyLeaseConfig
from runtime.safety.managed_guard import install_managed_runtime_safety
from runtime.safety.runtime_guard import RuntimeSafetyError
from runtime.safety.output_policy import OutputRequest, SafetySupervisor
from application.safe_output_coordinator import SafeOutputCoordinator
from tests.test_edge_safety_lease import FakeHass as FakeEdge
from tests.test_managed_runtime_safety import V2RuntimeSafetyTests
from tests.test_runtime_edge_lease import FakeApp as EdgeFakeApp, FakeHass, live_state


class DeferredProxy:
    """Small proxy matching composition-time attribute forwarding semantics."""
    def __init__(self):
        self.client = None

    def __getattr__(self, name):
        return getattr(self.client, name)


class CoordinatorClient(FakeHass):
    def __init__(self, **kwargs):
        fixture_live = live_state(switch="off", current=0.0, voltage=0.0, **kwargs)
        # This healthy simulated RD has a known raw R16=0. OVP/OCP bits
        # alone are not protection evidence; OPP/unknown R16 remains guarded.
        fixture_live.setdefault("protection_code", 0)
        initial = V2RuntimeSafetyTests._with_freshness(fixture_live)
        super().__init__(initial)
        self.safe_requests = []

    async def turn_on(self, entity_id=None):
        self.live["voltage"] = float(self.live.get("set_voltage", 0.0))
        return await super().turn_on(entity_id)

    async def turn_off(self, entity_id=None):
        result = await super().turn_off(entity_id)
        meta = self.live.setdefault("_meta", {}).setdefault("switch", {})
        stamp = datetime.now(timezone.utc).isoformat()
        meta.update(status="ok", age_s=0.0, last_reported=stamp, last_updated=stamp)
        return result

    async def set_voltage(self, value):
        await super().set_voltage(value)
        self.live["set_voltage_readback_v2"] = float(value)
        return True

    async def set_current(self, value):
        await super().set_current(value)
        return True

    async def safe_enable_output(self, **request):
        self.safe_requests.append(dict(request))
        return await SafeOutputCoordinator(self, SafetySupervisor()).enable(
            OutputRequest(**request)
        )


class D118LeaseRepairTests(unittest.IsolatedAsyncioTestCase):
    def _bind_guard(self, *, lease_ack: bool):
        proxy = DeferredProxy()
        proxy.client = FakeHass(live_state(switch="off", current=0.0))
        app = EdgeFakeApp(state=live_state(switch="off", current=0.0))
        app.hass = proxy
        edge = FakeEdge()
        edge.renew_ack = lease_ack
        app.edge_safety_lease = EdgeSafetyLease(edge, EdgeSafetyLeaseConfig(
            ack_attempts=1, ack_delay_s=0,
            disarm_ack_attempts=1, disarm_ack_delay_s=0,
        ))
        guard = install_managed_runtime_safety(app, patch_adapter=True)
        guard.OFF_CONFIRMATION_WINDOW_S = 0
        guard.OFF_CONFIRMATION_POLL_S = 0
        app.charge_controller.stop = lambda clear_session=True: setattr(
            app.charge_controller, "is_active", False
        )
        client = CoordinatorClient()
        proxy.client = client
        guard.bind_adapter(client)
        return app, proxy, client, guard

    async def test_safe_enable_coordinator_crosses_live_guard_and_bad_ack_never_turns_on(self):
        app, proxy, client, guard = self._bind_guard(lease_ack=False)
        result = await proxy.safe_enable_output(
            voltage_v=15.5, current_a=2.0,
            recipe_voltage_ceiling_v=15.5,
        )
        self.assertFalse(result.enabled)
        self.assertEqual(client.safe_requests[0]["voltage_v"], 15.5)
        self.assertEqual(client.turn_on_calls, 0)
        self.assertEqual(client.live["switch"], "off")

    async def test_armed_start_through_bound_client_uses_lease_then_verified_on(self):
        app, proxy, client, guard = self._bind_guard(lease_ack=True)
        result = await proxy.safe_enable_output(
            voltage_v=15.5, current_a=2.0,
            recipe_voltage_ceiling_v=15.5,
        )
        self.assertTrue(result.enabled, result.detail)
        self.assertEqual(client.turn_on_calls, 1)
        self.assertEqual(client.live["switch"], "on")
        self.assertEqual(
            app.edge_safety_lease.hass.presses.count(app.edge_safety_lease.config.renew_entity),
            1,
        )

    async def test_suspended_lease_while_native_output_on_stops_and_retires_after_off(self):
        app, proxy, client, _guard = self._bind_guard(lease_ack=True)
        fixture = json.loads(Path("tests/fixtures/d118_node104_start_failures.json").read_text())
        scenario = fixture["scenarios"][1]
        self.assertEqual(scenario["id"], "2026-10-18T18:05:24Z")
        app.edge_safety_lease.suspend_renewals()
        client.live["switch"] = "on"
        client.live["voltage"] = client.live["set_voltage"]
        with self.assertRaisesRegex(RuntimeSafetyError, "suspended"):
            await proxy.get_all_live()
        state = await app.edge_safety_lease.read_state()
        self.assertEqual(client.live["switch"], "off")
        self.assertFalse(state.armed)
        self.assertFalse(app.charge_controller.is_active)

    async def test_d118_incident_fixtures_pin_both_failed_start_outcomes(self):
        fixture = json.loads(Path("tests/fixtures/d118_node104_start_failures.json").read_text())
        self.assertEqual([item["id"] for item in fixture["scenarios"]], [
            "2026-10-18T18:03:14Z", "2026-10-18T18:05:24Z",
        ])
        for scenario in fixture["scenarios"]:
            self.assertEqual(scenario["expected"], {
                "edge_armed": False, "output_on": False, "session_active": False,
            })

    def test_start_callback_acknowledged_only_once_and_uses_message_result(self):
        source = Path("production_bootstrap.py").read_text(encoding="utf-8")
        route = source.split("async def _battery_start_route", 1)[1]
        route = route.split("production_bot_ui.install_ui_support", 1)[0]
        self.assertEqual(route.count("call.answer("), 1)
        self.assertIn("_send_result(", route)
        self.assertIn('getattr(message, "answer", None)', route)

    def test_start_marks_enable_submitted_before_port_call_and_reuses_one_settlement_task(self):
        source = Path("application/start_transaction_service.py").read_text(encoding="utf-8")
        transaction = source.split("enable_submitted = False", 1)[1]
        submitted = transaction.index("enable_submitted = True")
        port_enable = transaction.index("result = await port.enable(")
        self.assertLess(submitted, port_enable)

        cancellation = transaction.split("except asyncio.CancelledError:", 1)[1]
        self.assertIn("if settlement_task is None:", cancellation)
        self.assertIn("settlement_task = asyncio.create_task(settle_submitted_enable())", cancellation)
        self.assertIn("await asyncio.shield(settlement_task)", cancellation)
        self.assertIn("while not settlement_task.done():", cancellation)

        decorator = source.split("def _serialized_charge_start", 1)[1]
        decorator = decorator.split("@_serialized_charge_start", 1)[0]
        self.assertIn("lock = port._guard_owner_lock", decorator)
        self.assertIn("async with lock:", decorator)
        self.assertIn('raise RuntimeError("START cannot run without canonical owner lock")', decorator)

    def test_production_deferred_bind_reinstalls_guard_on_live_client(self):
        source = Path("runtime/production_runtime.py").read_text(encoding="utf-8")
        bind = source.split("def bind(self, client: HassClient)", 1)[1]
        bind = bind.split("def set_initializer", 1)[0]
        self.assertIn('getattr(guard, "bind_adapter", None)', bind)
        self.assertIn("bind_adapter(client)", bind)

    def test_failed_start_retires_session_only_after_verified_off(self):
        source = Path("application/start_transaction_service.py").read_text(encoding="utf-8")
        self.assertIn("if not result.verified:", source)
        failed_result = source.split("if not result.verified:", 1)[1]
        failed_result = failed_result.split("if recipe_binding is not None:", 1)[0]
        self.assertIn("settlement_task = asyncio.create_task(settle_submitted_enable())", failed_result)
        self.assertIn("off_settled = await asyncio.shield(settlement_task)", failed_result)
        self.assertIn("START_PENDING точно отменён", failed_result)
        self.assertIn("START_PENDING сохранён", failed_result)

        settlement = source.split("async def settle_submitted_enable()", 1)[1]
        settlement = settlement.split("def project_live_against_prior()", 1)[0]
        self.assertIn("request_emergency_off_receipt()", settlement)
        self.assertIn("native_off_timestamp_after_receipt(", settlement)
        self.assertIn("connection_generation=receipt.connection_generation", settlement)
        self.assertIn("live_controller.stop(clear_session=False)", settlement)
        self.assertIn("return rollback_pending()", settlement)
        self.assertNotIn("clear_session=True", settlement)


if __name__ == "__main__":
    unittest.main()
