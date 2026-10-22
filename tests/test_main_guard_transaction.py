"""Offline execution-port MAIN Guard transaction: no real hardware or HA."""
import asyncio
from dataclasses import replace
import unittest

from application.execution_port import ExecutionPort
from application.guard_execution_owner_lock import GuardExecutionOwnerLock
from application.main_guard_transaction import MainGuardAuthority
from runtime.charge.strategy.main_current_guard import MainCurrentGuard


class FakeOwner:
    def __init__(self):
        self.live = {
            "output_state_code_v2": 1, "current": 4.0,
            "set_current_readback_v2": 7.2, "ocp_readback_v2": 7.3,
            "protection_code": 0,
        }
        self.live["_meta"] = {
            key: {"status": "ok", "age_s": 0.1,
                  "source": "esp_native_api", "native_type": "SensorState",
                  "subscription_timestamp_monotonic": 100.0}
            for key in ("output_state_code_v2", "current",
                        "set_current_readback_v2", "ocp_readback_v2",
                        "protection_code")
        }
        self.events = []
        self.mirror = True
        self.refuse_off = False

    async def get_all_live(self):
        return dict(self.live, _meta={k: dict(v) for k, v in self.live["_meta"].items()})

    async def set_current(self, value):
        self.events.append(("set_current", round(value, 3)))
        if self.mirror:
            self.live["set_current_readback_v2"] = value
        return True

    async def set_ocp(self, value):
        self.events.append(("set_ocp", round(value, 3)))
        if self.mirror:
            self.live["ocp_readback_v2"] = value
        return True

    async def turn_off(self):
        self.events.append(("OFF",))
        if self.refuse_off:
            return False
        self.live["output_state_code_v2"] = 0
        return True


def pending():
    state = MainCurrentGuard.start(
        session_id="real-session", battery_id="bat", segment_id="main-1",
        capacity_ah=72, recipe_initial_current_a=12
    )
    proposal = None
    for ts in range(0, 1801, 30):
        state, proposal = state.observe(
            now_s=ts, output_on=True, measured_current_a=4, fresh=True)
    return state, proposal


class MainGuardTransactionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.owner = FakeOwner()
        self.port = ExecutionPort(self.owner)
        self.guard, self.proposal = pending()
        self.snapshots = []
        self.fail_commit = False
        self.lock = GuardExecutionOwnerLock()
        self.port.bind_guard_owner_lock(self.lock)

    async def save(self, snapshot):
        self.snapshots.append(snapshot)
        if self.fail_commit and snapshot["pending"] is None:
            raise OSError("forced durable commit failure")

    async def transact(self, **overrides):
        args = dict(
            guard=self.guard, proposal=self.proposal,
            authority=MainGuardAuthority(
                session_id="real-session", battery_id="bat", segment_id="main-1",
                profile="EFB", stage="Main Charge",
                lease_armed=True, owner_authorized=True,
            ),
            persist=self.save, execution_lock=self.lock, now=lambda: 1801.0,
            max_stage_current_a=12.0, ocp_offset_a=0.1,
            stabilize_delay_s=0.0,
        )
        args.update(overrides)
        return await self.port.execute_main_current_guard_reduction(**args)

    async def test_positive_protected_downward_order_and_journal(self):
        result = await self.transact()
        self.assertTrue(result.verified)
        self.assertEqual(result.guard.hardware_limit_a, 5)
        self.assertIsNone(result.guard.pending)
        self.assertEqual(self.owner.events, [("set_current", 5.0), ("set_ocp", 5.1)])
        self.assertEqual(len(self.snapshots), 2)
        self.assertIsNotNone(self.snapshots[0]["pending"])
        self.assertIsNone(self.snapshots[1]["pending"])

    async def test_stale_output_evidence_denies_without_physical_write(self):
        self.owner.live["_meta"]["output_state_code_v2"]["age_s"] = 60
        result = await self.transact()
        self.assertFalse(result.verified)
        self.assertFalse(result.off_confirmed)
        self.assertEqual(self.owner.events, [])
        self.assertEqual(self.snapshots, [])

    async def test_legacy_value_never_replaces_missing_v2_current(self):
        del self.owner.live["_meta"]["set_current_readback_v2"]
        self.owner.live["set_current"] = 7.2
        result = await self.transact()
        self.assertFalse(result.verified)
        self.assertEqual(self.owner.events, [])

    async def test_stale_ocp_or_unknown_protection_rejects(self):
        self.owner.live["_meta"]["ocp_readback_v2"]["status"] = "stale"
        self.assertFalse((await self.transact()).verified)
        self.assertEqual(self.owner.events, [])

    async def test_confirmed_native_protection_trip_requests_verified_off(self):
        self.owner.live["protection_code"] = 1
        result = await self.transact()
        self.assertFalse(result.verified)
        self.assertTrue(result.off_confirmed)
        self.assertEqual(self.owner.events, [("OFF",)])

    async def test_unknown_or_invalid_protection_code_does_not_count_as_trip(self):
        for value in (None, "unknown", float("nan")):
            with self.subTest(value=value):
                self.owner.live["protection_code"] = value
                result = await self.transact()
                self.assertFalse(result.verified)
                self.assertFalse(result.off_confirmed)
                self.assertEqual(self.owner.events, [])

    async def test_confirmed_upward_current_readback_requests_off_prewrite(self):
        self.owner.live["set_current_readback_v2"] = 7.23
        result = await self.transact()
        self.assertFalse(result.verified)
        self.assertTrue(result.off_confirmed)
        self.assertEqual(self.owner.events, [("OFF",)])

    async def test_confirmed_upward_ocp_readback_requests_off_prewrite(self):
        self.owner.live["ocp_readback_v2"] = 7.33
        result = await self.transact()
        self.assertFalse(result.verified)
        self.assertTrue(result.off_confirmed)
        self.assertEqual(self.owner.events, [("OFF",)])

    async def test_wrong_preflight_programmed_current_rejects(self):
        self.owner.live["set_current_readback_v2"] = 5.0
        result = await self.transact()
        self.assertFalse(result.verified)
        self.assertEqual(self.owner.events, [])

    async def test_wrong_ocp_margin_rejects_before_any_write(self):
        self.owner.live["ocp_readback_v2"] = 7.0
        result = await self.transact()
        self.assertFalse(result.verified)
        self.assertEqual(self.owner.events, [])

    async def test_fresh_native_protection_trip_forces_verified_off_prewrite(self):
        self.owner.live["protection_code"] = 2
        result = await self.transact()
        self.assertFalse(result.verified)
        self.assertTrue(result.off_confirmed)
        self.assertEqual(self.owner.events, [("OFF",)])
        self.assertEqual(self.snapshots, [])

    async def test_unknown_native_protection_code_denies_without_off(self):
        self.owner.live["protection_code"] = 4
        result = await self.transact()
        self.assertFalse(result.verified)
        self.assertFalse(result.off_confirmed)
        self.assertEqual(self.owner.events, [])

    async def test_fresh_upward_iset_deviation_forces_verified_off_prewrite(self):
        self.owner.live["set_current_readback_v2"] = 8.0
        result = await self.transact()
        self.assertFalse(result.verified)
        self.assertTrue(result.off_confirmed)
        self.assertEqual(self.owner.events, [("OFF",)])
        self.assertEqual(self.snapshots, [])

    async def test_fresh_upward_ocp_deviation_forces_verified_off_prewrite(self):
        self.owner.live["ocp_readback_v2"] = 8.0
        result = await self.transact()
        self.assertFalse(result.verified)
        self.assertTrue(result.off_confirmed)
        self.assertEqual(self.owner.events, [("OFF",)])
        self.assertEqual(self.snapshots, [])

    async def test_unconfirmed_setter_fail_closed_and_no_commit(self):
        self.owner.mirror = False
        result = await self.transact()
        self.assertFalse(result.verified)
        self.assertTrue(result.off_confirmed)
        self.assertEqual(self.owner.events,
                         [("set_current", 5.0), ("set_ocp", 5.1), ("OFF",)])
        self.assertEqual(len(self.snapshots), 1)
        self.assertIsNotNone(self.snapshots[0]["pending"])

    async def test_postflight_ack_rejection_preserves_guard_fault_and_readback_diagnostic(self):
        original = self.owner.set_current

        async def quantized_but_outside_guard_tolerance(value):
            await original(value)
            # Model a fresh native Iset register report outside the documented
            # 0.02 A acknowledgement tolerance. Do not weaken that tolerance.
            self.owner.live["set_current_readback_v2"] = value + 0.03

        self.owner.set_current = quantized_but_outside_guard_tolerance
        result = await self.transact()
        self.assertFalse(result.verified)
        self.assertTrue(result.off_confirmed)
        self.assertIn("postflight_guard_ack_rejected:programmed_current_readback_mismatch",
                      result.reason)
        self.assertEqual(result.diagnostic["iset_target_a"], 5.0)
        self.assertAlmostEqual(result.diagnostic["iset_delta_a"], 0.03)
        self.assertEqual(result.diagnostic["readback_tolerance_a"], 0.02)
        self.assertEqual(self.owner.events[-1], ("OFF",))
        self.assertEqual(len(self.snapshots), 1)

    async def test_persistence_failure_after_hardware_ack_forces_off(self):
        self.fail_commit = True
        result = await self.transact()
        self.assertFalse(result.verified)
        self.assertTrue(result.off_confirmed)
        self.assertEqual(self.owner.events[-1], ("OFF",))
        self.assertEqual(len(self.snapshots), 2)

    async def test_persistence_failure_before_write_is_read_only_deny(self):
        async def fail_before(_):
            raise OSError("disk failure")
        result = await self.transact(persist=fail_before)
        self.assertFalse(result.verified)
        self.assertFalse(result.off_confirmed)
        self.assertEqual(self.owner.events, [])

    async def test_expired_proposal_fails_closed(self):
        result = await self.transact(now=lambda: 2200)
        self.assertFalse(result.verified)
        self.assertEqual(self.owner.events, [])

    async def test_no_valid_identity_or_pending_refuses_current_write(self):
        result = await self.transact(guard=replace(self.guard, pending=None))
        self.assertFalse(result.verified)
        self.assertEqual(self.owner.events, [])

    async def test_unverified_off_is_not_misreported_as_contained(self):
        self.owner.refuse_off = True
        self.owner.mirror = False
        result = await self.transact()
        self.assertFalse(result.verified)
        self.assertFalse(result.off_confirmed)
        self.assertEqual(self.owner.events[-1], ("OFF",))

    async def test_missing_shared_lock_fails_before_hardware(self):
        with self.assertRaises(TypeError):
            await self.transact(execution_lock=None)
        self.assertEqual(self.owner.events, [])

    async def test_unrelated_lock_does_not_simulate_owner_serialization(self):
        with self.assertRaisesRegex(TypeError, "not bound"):
            await self.transact(execution_lock=asyncio.Lock())
        self.assertEqual(self.owner.events, [])

    async def test_guard_transaction_refuses_unbound_port(self):
        self.port = ExecutionPort(self.owner)
        with self.assertRaisesRegex(TypeError, "not bound"):
            await self.transact()
        self.assertEqual(self.owner.events, [])

    async def test_owner_lock_cannot_be_silently_replaced(self):
        with self.assertRaises(RuntimeError):
            self.port.bind_guard_owner_lock(asyncio.Lock())
        self.port.bind_guard_owner_lock(self.lock)

    async def test_fresh_ha_last_reported_metadata_without_age_s(self):
        from datetime import datetime, timezone
        stamp = datetime.now(timezone.utc).isoformat()
        for entry in self.owner.live["_meta"].values():
            entry.pop("age_s", None)
            entry["last_reported"] = stamp
        result = await self.transact()
        self.assertTrue(result.verified)

    async def test_stale_last_reported_and_skewed_heartbeat_rejected(self):
        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc)
        for entry in self.owner.live["_meta"].values():
            entry.pop("age_s", None)
            entry["last_reported"] = now.isoformat()
        self.owner.live["_meta"]["ocp_readback_v2"]["last_reported"] = (
            now - timedelta(seconds=25)
        ).isoformat()
        result = await self.transact()
        self.assertFalse(result.verified)
        self.assertEqual(self.owner.events, [])

    async def test_session_identity_stage_lease_and_owner_gates(self):
        original = MainGuardAuthority(
            session_id="real-session", battery_id="bat", segment_id="main-1",
            profile="EFB", stage="Main Charge",
            lease_armed=True, owner_authorized=True,
        )
        for patch in (
            {"session_id": "wrong"}, {"battery_id": "wrong"},
            {"segment_id": "wrong"}, {"profile": "AGM"},
            {"stage": "Mix Mode"}, {"lease_armed": False},
            {"owner_authorized": False},
        ):
            with self.subTest(patch=patch):
                self.owner.events.clear()
                result = await self.transact(authority=replace(original, **patch))
                self.assertFalse(result.verified)
                self.assertFalse(result.off_confirmed)
                self.assertEqual(self.owner.events, [])
                self.owner.live["output_state_code_v2"] = 1

    async def test_output_on_value_must_be_known_v2_register(self):
        self.owner.live["output_state_code_v2"] = None
        result = await self.transact()
        self.assertFalse(result.verified)
        self.assertEqual(self.owner.events, [])


if __name__ == "__main__":
    unittest.main()
