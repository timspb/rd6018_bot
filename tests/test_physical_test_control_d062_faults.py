import types
import unittest
from dataclasses import dataclass
from unittest.mock import patch

from ha_history import ContinuousOnEvidence, MixHistoryEvidence
from pb_domain import BatteryChemistry
from rd_managed_adoption import ManagedAdoptionFingerprint
from rd_managed_mix import ManagedMixState
from runtime_safety import RuntimeSafetyError

from physical_test_control_d062 import install_physical_test_control_d062


@dataclass
class FakeIdentity:
    battery_id: str = "varta_agm80_a0019828108"
    chemistry: BatteryChemistry = BatteryChemistry.AGM
    nominal_capacity_ah: float = 80.0


class FakeControl:
    def __init__(self, app):
        import asyncio
        self.app = app
        self._operation_lock = asyncio.Lock()
        self.live = {
            "switch": "on",
            "output_state_code_v2": 1,
            "set_voltage": 15.10,
            "set_current": 0.18,
            "ovp": 15.30,
            "ocp": 0.40,
        }
        self._status = self.base_status
        self.dispatch = self.base_dispatch

    async def base_status(self):
        return {"rd_control_mode": "hands_off"}

    async def base_dispatch(self, request):
        return {"ok": True, "operation": "base"}

    async def _raw_live(self):
        return dict(self.live)

    @staticmethod
    def _is_on(live):
        return (
            live.get("switch") == "on"
            and float(live.get("output_state_code_v2")) == 1.0
        )

    @staticmethod
    def _is_off(live):
        return (
            live.get("switch") == "off"
            and float(live.get("output_state_code_v2")) == 0.0
        )

    @staticmethod
    def _fingerprint(value):
        if value is None:
            return None
        return {
            "set_voltage_v": float(value.set_voltage_v),
            "set_current_a": float(value.set_current_a),
            "ovp_v": float(value.ovp_v),
            "ocp_a": float(value.ocp_a),
        }

    @staticmethod
    def _require_fields(request, fields):
        if set(request) != fields:
            raise ValueError("unexpected or missing request fields")

    @staticmethod
    def _error(message):
        return {"ok": False, "error": str(message)}


@dataclass
class LeaseState:
    generation: int
    armed: bool
    remaining_s: float


class FaultLease:
    def __init__(self):
        self.config = types.SimpleNamespace(ack_attempts=3)
        self.state = LeaseState(generation=41, armed=False, remaining_s=0.0)

    async def read_state(self):
        return self.state

    async def _press(self, entity_id):
        if entity_id != "button.edge_adopt":
            return False
        self.state = LeaseState(
            generation=self.state.generation + 1,
            armed=True,
            remaining_s=900.0,
        )
        return True


class FaultEdge:
    def __init__(self, lease):
        self.lease = lease
        self.config = types.SimpleNamespace(entity="button.edge_adopt")
        self.command_may_have_executed = False

    async def prepare(self):
        self.command_may_have_executed = False
        return await self.lease.read_state()

    async def adopt(self, *, expected_generation=None):
        before = await self.lease.read_state()
        if expected_generation is not None and before.generation != expected_generation:
            raise RuntimeSafetyError("generation changed before edge command")
        self.command_may_have_executed = True
        if not await self.lease._press(self.config.entity):
            raise RuntimeSafetyError("edge command rejected")
        latest = before
        for _ in range(self.lease.config.ack_attempts):
            latest = await self.lease.read_state()
            if latest.armed and latest.generation != before.generation:
                return latest
        raise RuntimeSafetyError(
            "edge live adoption was not positively acknowledged by generation/readback"
        )


class FaultGuard:
    def __init__(self, control):
        self.control = control

    async def _raw_live(self):
        return dict(self.control.live)


class FaultD061:
    @staticmethod
    def _fingerprint(live):
        return ManagedAdoptionFingerprint(
            float(live["set_voltage"]),
            float(live["set_current"]),
            float(live["ovp"]),
            float(live["ocp"]),
        )

    def _preflight_live(self, live, *, expected=None):
        if live.get("switch") != "on":
            raise RuntimeSafetyError("Output must remain ON")
        fingerprint = self._fingerprint(live)
        if expected is not None and fingerprint != expected:
            raise RuntimeSafetyError("live RD setpoints changed during adoption")
        return fingerprint


class HistoryReader:
    async def read_mix_evidence(self, *, live=None, lookback_s=None):
        return MixHistoryEvidence(
            fetched_at_s=2_000_000_000.0,
            output=ContinuousOnEvidence(
                reliable=False,
                started_at_s=None,
                elapsed_s=None,
                reason="window starts ON",
            ),
        )


class FaultCoordinator:
    def __init__(self, app, control, d061):
        self.app = app
        self.guard = FaultGuard(control)
        self.edge = FaultEdge(FaultLease())
        self.d061 = d061
        self.history_reader = HistoryReader()
        self.state = ManagedMixState.IDLE
        self.battery_id = ""
        self.chemistry = None
        self.prior_elapsed_s = 0.0
        self.prior_age_source = ""
        self.adopted_active_elapsed_s = 0.0
        self.max_authority = None
        self.current_authority = None
        self.finish_hold_started_at_s = None
        self.terminal_reason = ""
        self.last_status = ""

    @property
    def managed_authority(self):
        return self.state in {ManagedMixState.ACTIVE, ManagedMixState.OFF_PENDING}

    @property
    def total_active_elapsed_s(self):
        return self.prior_elapsed_s + self.adopted_active_elapsed_s

    @property
    def remaining_budget_s(self):
        return None

    def _wall_time(self):
        return 2_000_000_000.0

    def _conflict(self):
        return None

    def _chemistry_preflight(self, chemistry, capacity_ah, fingerprint):
        if chemistry is not BatteryChemistry.AGM:
            raise RuntimeSafetyError("expected AGM")
        if fingerprint.set_voltage_v < 15.0:
            raise RuntimeSafetyError("not high-voltage Mix")

    async def adopt(self, preview):
        edge_uncertain = False
        try:
            first = await self.guard._raw_live()
            self.d061._preflight_live(first, expected=preview.fingerprint)
            self.state = ManagedMixState.ADOPTION_PENDING
            prepared = await self.edge.prepare()
            second = await self.guard._raw_live()
            self.d061._preflight_live(second, expected=preview.fingerprint)
            try:
                await self.edge.adopt(expected_generation=prepared.generation)
            finally:
                edge_uncertain = bool(self.edge.command_may_have_executed)
            third = await self.guard._raw_live()
            fingerprint = self.d061._preflight_live(
                third, expected=preview.fingerprint
            )
            self.state = ManagedMixState.ACTIVE
            self.current_authority = fingerprint
            self.max_authority = fingerprint
            return True
        except Exception as exc:
            if edge_uncertain:
                self.control.live["switch"] = "off"
                self.control.live["output_state_code_v2"] = 0
                self.edge.lease.state = LeaseState(
                    generation=self.edge.lease.state.generation,
                    armed=False,
                    remaining_s=0.0,
                )
                self.state = ManagedMixState.FAILED
                self.terminal_reason = (
                    f"MIX_ADOPTED_INCOMPLETE_AFTER_EDGE:{type(exc).__name__}:{exc}"
                )
            else:
                self.state = ManagedMixState.FAILED
                self.terminal_reason = "ADOPTION_PREFLIGHT_FAILED"
            raise

    @property
    def control(self):
        return self.guard.control


class D062PhysicalFaultControlTests(unittest.IsolatedAsyncioTestCase):
    def make_system(self):
        app = types.SimpleNamespace()
        app.rd_control_mode_manager = types.SimpleNamespace(hands_off=True)
        control = FakeControl(app)
        d061 = FaultD061()
        app.rd_managed_live_adoption = d061
        coordinator = FaultCoordinator(app, control, d061)
        app.rd_managed_mix_adoption = coordinator
        extension = install_physical_test_control_d062(app, control)
        return app, control, extension, coordinator

    async def test_d062_toctou_hook_rejects_before_edge_without_actuation(self):
        _app, control, _extension, coordinator = self.make_system()
        record = types.SimpleNamespace(identity=FakeIdentity())
        with patch("physical_test_control_d062.get_battery", return_value=record):
            result = await control.dispatch(
                {
                    "op": "d062_fault_toctou_precommand",
                    "battery_id": record.identity.battery_id,
                    "remaining_budget_s": 300,
                }
            )
        self.assertTrue(result["ok"])
        evidence = result["result"]
        self.assertTrue(evidence["rejected"])
        self.assertFalse(evidence["command_may_have_executed"])
        self.assertEqual(evidence["generation_before"], evidence["generation_after"])
        self.assertEqual(evidence["hardware_writes_injected"], 0)
        self.assertEqual(control.live["switch"], "on")
        self.assertEqual(coordinator.state, ManagedMixState.FAILED)
        self.assertEqual(coordinator.terminal_reason, "ADOPTION_PREFLIGHT_FAILED")

    async def test_d062_ambiguous_ack_crosses_real_edge_then_contains_off(self):
        _app, control, _extension, coordinator = self.make_system()
        record = types.SimpleNamespace(identity=FakeIdentity())
        with patch("physical_test_control_d062.get_battery", return_value=record):
            result = await control.dispatch(
                {
                    "op": "d062_fault_ambiguous_edge_ack",
                    "battery_id": record.identity.battery_id,
                    "remaining_budget_s": 300,
                }
            )
        self.assertTrue(result["ok"])
        evidence = result["result"]
        self.assertTrue(evidence["contained"])
        self.assertTrue(evidence["command_may_have_executed"])
        self.assertEqual(
            evidence["generation_after"], evidence["generation_before"] + 1
        )
        self.assertFalse(evidence["lease_armed"])
        self.assertEqual(evidence["remaining_s"], 0.0)
        self.assertEqual(control.live["switch"], "off")
        self.assertEqual(coordinator.state, ManagedMixState.FAILED)
        self.assertIn("MIX_ADOPTED_INCOMPLETE_AFTER_EDGE", evidence["terminal_reason"])

    async def test_d062_fault_operations_reject_widening_or_extra_fields(self):
        _app, control, _extension, _coordinator = self.make_system()
        result = await control.dispatch(
            {
                "op": "d062_fault_toctou_precommand",
                "battery_id": "varta_agm80_a0019828108",
                "remaining_budget_s": 300,
                "set_voltage": 16.0,
            }
        )
        self.assertFalse(result["ok"])
        self.assertIn("unexpected or missing", result["error"])


if __name__ == "__main__":
    unittest.main()
