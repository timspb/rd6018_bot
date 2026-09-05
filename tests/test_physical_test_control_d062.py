import asyncio
import types
import unittest
from dataclasses import dataclass
from unittest.mock import patch

from ha_history import ContinuousOnEvidence, MixHistoryEvidence
from pb_domain import BatteryChemistry
from rd_managed_adoption import ManagedAdoptionFingerprint
from rd_managed_mix import ManagedMixState, PriorMixAgeSource

from physical_test_control_d062 import (
    PhysicalTestControlD062,
    install_physical_test_control_d062,
)


@dataclass
class FakeIdentity:
    battery_id: str = "varta_agm80_a0019828108"
    chemistry: BatteryChemistry = BatteryChemistry.AGM
    nominal_capacity_ah: float = 80.0


class FakeHistoryReader:
    def __init__(self, history):
        self.history = history
        self.calls = 0

    async def read_mix_evidence(self, *, live=None, lookback_s=None):
        self.calls += 1
        return self.history


def history(*, elapsed_s=None, reliable=False, fetched_at_s=2_000_000_000.0):
    return MixHistoryEvidence(
        fetched_at_s=fetched_at_s,
        output=ContinuousOnEvidence(
            reliable=bool(reliable),
            started_at_s=(
                fetched_at_s - float(elapsed_s)
                if reliable and elapsed_s is not None
                else None
            ),
            elapsed_s=float(elapsed_s) if reliable and elapsed_s is not None else None,
            reason=(
                "explicit Recorder OFF->ON edge"
                if reliable
                else "window starts ON"
            ),
        ),
    )


class FakeControl:
    def __init__(self, app):
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
        self.base_dispatch_calls = 0
        self._status = self.base_status
        self.dispatch = self.base_dispatch

    async def base_status(self):
        return {"rd_control_mode": "hands_off"}

    async def base_dispatch(self, request):
        self.base_dispatch_calls += 1
        return {"ok": True, "operation": "base"}

    async def _raw_live(self):
        return dict(self.live)

    @staticmethod
    def _is_on(live):
        return live.get("switch") == "on" and float(live.get("output_state_code_v2")) == 1.0

    @staticmethod
    def _is_off(live):
        return live.get("switch") == "off" and float(live.get("output_state_code_v2")) == 0.0

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


class FakeD061:
    @staticmethod
    def _preflight_live(live):
        return ManagedAdoptionFingerprint(
            float(live["set_voltage"]),
            float(live["set_current"]),
            float(live["ovp"]),
            float(live["ocp"]),
        )


class FakeCoordinator:
    def __init__(self, reader):
        self.history_reader = reader
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
        self.preview = None
        self.managed_authority = False
        self.stop_calls = 0
        self.chemistry_preflight_calls = 0
        self.now = 2_000_000_000.0

    @property
    def total_active_elapsed_s(self):
        return self.prior_elapsed_s + self.adopted_active_elapsed_s

    @property
    def remaining_budget_s(self):
        if self.chemistry is None:
            return None
        hard = {
            BatteryChemistry.AGM: 10.0,
            BatteryChemistry.EFB: 24.0,
            BatteryChemistry.CA_CA: 20.0,
            BatteryChemistry.FLOODED: 20.0,
        }[self.chemistry] * 3600.0
        return max(0.0, hard - self.total_active_elapsed_s)

    def _wall_time(self):
        return self.now

    def _conflict(self):
        return None

    def _chemistry_preflight(self, chemistry, capacity_ah, fingerprint):
        self.chemistry_preflight_calls += 1
        if chemistry is BatteryChemistry.AGM and fingerprint.set_voltage_v <= 15.08:
            raise RuntimeError("not high-voltage Mix")

    async def adopt(self, preview):
        self.preview = preview
        self.state = ManagedMixState.ACTIVE
        self.managed_authority = True
        self.battery_id = preview.battery_id
        self.chemistry = preview.chemistry
        self.prior_elapsed_s = preview.prior_age.elapsed_s
        self.prior_age_source = preview.prior_age.source.value
        self.max_authority = preview.fingerprint
        self.current_authority = preview.fingerprint
        return True

    async def stop_by_operator(self):
        self.stop_calls += 1
        self.managed_authority = False
        self.state = ManagedMixState.COMPLETED
        return True


class PhysicalTestControlD062Tests(unittest.IsolatedAsyncioTestCase):
    def make_system(self, recorder_history):
        app = types.SimpleNamespace()
        reader = FakeHistoryReader(recorder_history)
        coordinator = FakeCoordinator(reader)
        app.rd_managed_mix_adoption = coordinator
        app.rd_managed_live_adoption = FakeD061()
        app.rd_control_mode_manager = types.SimpleNamespace(hands_off=True)
        control = FakeControl(app)
        extension = install_physical_test_control_d062(app, control)
        return app, control, extension, coordinator

    async def test_d063_unknown_recorder_age_stays_unknown_not_zero(self):
        _app, control, _extension, _coordinator = self.make_system(history())
        result = await control.dispatch({"op": "d063_prior_age"})
        self.assertTrue(result["ok"])
        evidence = result["result"]
        self.assertFalse(evidence["proven"])
        self.assertIsNone(evidence["resolved_elapsed_s"])
        self.assertIsNone(evidence["source"])
        self.assertIn("window starts ON", evidence["reason"])

    async def test_d063_reliable_recorder_edge_is_reported_as_proven(self):
        _app, control, _extension, _coordinator = self.make_system(
            history(elapsed_s=123.0, reliable=True)
        )
        result = await control.dispatch({"op": "d063_prior_age"})
        self.assertTrue(result["result"]["proven"])
        self.assertEqual(result["result"]["source"], "recorder")
        self.assertAlmostEqual(result["result"]["resolved_elapsed_s"], 123.0)

    async def test_d062_test_budget_is_conservative_operator_declared_floor(self):
        _app, control, _extension, coordinator = self.make_system(
            history(elapsed_s=60.0, reliable=True)
        )
        record = types.SimpleNamespace(identity=FakeIdentity())
        with patch("physical_test_control_d062.get_battery", return_value=record):
            result = await control.dispatch(
                {
                    "op": "d062_adopt_test_budget",
                    "battery_id": record.identity.battery_id,
                    "remaining_budget_s": 60,
                }
            )
        self.assertTrue(result["ok"])
        self.assertTrue(result["result"]["adopted"])
        self.assertEqual(
            coordinator.preview.prior_age.source,
            PriorMixAgeSource.OPERATOR_DECLARED,
        )
        self.assertAlmostEqual(coordinator.remaining_budget_s, 60.0)
        self.assertEqual(coordinator.chemistry_preflight_calls, 1)
        self.assertEqual(
            result["result"]["authority"]["set_current_a"],
            0.18,
        )

    async def test_recorder_can_only_make_test_budget_older_not_fresher(self):
        recorder_elapsed = 10 * 3600 - 40
        _app, control, _extension, coordinator = self.make_system(
            history(elapsed_s=recorder_elapsed, reliable=True)
        )
        record = types.SimpleNamespace(identity=FakeIdentity())
        with patch("physical_test_control_d062.get_battery", return_value=record):
            result = await control.dispatch(
                {
                    "op": "d062_adopt_test_budget",
                    "battery_id": record.identity.battery_id,
                    "remaining_budget_s": 60,
                }
            )
        self.assertTrue(result["ok"])
        self.assertEqual(coordinator.preview.prior_age.source, PriorMixAgeSource.RECORDER)
        self.assertAlmostEqual(coordinator.remaining_budget_s, 40.0)

    async def test_budget_argument_cannot_grant_more_than_five_minutes(self):
        _app, control, _extension, _coordinator = self.make_system(history())
        result = await control.dispatch(
            {
                "op": "d062_adopt_test_budget",
                "battery_id": "varta_agm80_a0019828108",
                "remaining_budget_s": 301,
            }
        )
        self.assertFalse(result["ok"])
        self.assertIn("30..300", result["error"])

    async def test_d062_verified_stop_requires_and_retires_managed_authority(self):
        _app, control, _extension, coordinator = self.make_system(history())
        rejected = await control.dispatch({"op": "d062_verified_stop"})
        self.assertFalse(rejected["ok"])
        coordinator.managed_authority = True
        coordinator.state = ManagedMixState.ACTIVE

        async def stop():
            coordinator.stop_calls += 1
            coordinator.managed_authority = False
            coordinator.state = ManagedMixState.COMPLETED
            control.live["switch"] = "off"
            control.live["output_state_code_v2"] = 0
            return True

        coordinator.stop_by_operator = stop
        accepted = await control.dispatch({"op": "d062_verified_stop"})
        self.assertTrue(accepted["ok"])
        self.assertEqual(coordinator.stop_calls, 1)
        self.assertEqual(accepted["result"]["output_state_code_v2"], 0)

    async def test_status_is_extended_without_replacing_base_status(self):
        app, control, extension, _coordinator = self.make_system(history())
        self.assertIsInstance(extension, PhysicalTestControlD062)
        result = await control._status()
        self.assertEqual(result["rd_control_mode"], "hands_off")
        self.assertTrue(result["managed_mix"]["available"])
        self.assertEqual(result["managed_mix"]["state"], "idle")
        self.assertIs(install_physical_test_control_d062(app, control), extension)

    async def test_unknown_base_operations_are_delegated_unchanged(self):
        _app, control, _extension, _coordinator = self.make_system(history())
        result = await control.dispatch({"op": "status"})
        self.assertTrue(result["ok"])
        self.assertEqual(result["operation"], "base")
        self.assertEqual(control.base_dispatch_calls, 1)

    async def test_new_operations_reject_extra_fields(self):
        _app, control, _extension, _coordinator = self.make_system(history())
        result = await control.dispatch({"op": "d063_prior_age", "extra": 1})
        self.assertFalse(result["ok"])
        self.assertIn("unexpected or missing", result["error"])


if __name__ == "__main__":
    unittest.main()
