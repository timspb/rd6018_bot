import json
import tempfile
import types
import unittest

from rd_control_mode import RdControlModeManager
from rd_managed_mix import ManagedMixAdoptionCoordinator, ManagedMixState
from runtime_safety_v2 import V2RuntimeSafetyGuard


class DummyHass:
    def __init__(self):
        self.live = {
            "switch": "on",
            "set_voltage": 15.10,
            "set_current": 0.18,
            "ovp": 15.30,
            "ocp": 0.40,
        }
        self.turn_off_calls = 0
        self.writes = []

    @staticmethod
    def _entity_metadata(entity_id, data, status):
        return {
            "entity_id": entity_id,
            "status": status,
            "last_updated": data.get("last_updated"),
        }

    async def get_all_live(self):
        return dict(self.live)

    async def turn_on(self, entity_id=None):
        self.live["switch"] = "on"
        return True

    async def turn_off(self, entity_id=None):
        self.turn_off_calls += 1
        self.live["switch"] = "off"
        return True

    async def set_voltage(self, value):
        self.writes.append(("voltage", float(value)))
        return True

    async def set_current(self, value):
        self.writes.append(("current", float(value)))
        return True

    async def set_ovp(self, value):
        self.writes.append(("ovp", float(value)))
        return True

    async def set_ocp(self, value):
        self.writes.append(("ocp", float(value)))
        return True


class ResidualLease:
    def __init__(self):
        self.armed = True
        self.disarm_calls = 0

    async def disarm(self):
        self.disarm_calls += 1
        self.armed = False
        return True


class D062AmbiguousAckHandsOffDisarmTests(unittest.IsolatedAsyncioTestCase):
    async def test_ambiguous_edge_containment_disarms_residual_lease_after_verified_off(self):
        with tempfile.TemporaryDirectory() as tmp:
            mode_file = f"{tmp}/mode.json"
            with open(mode_file, "w", encoding="utf-8") as handle:
                json.dump({"version": 1, "mode": "hands_off", "updated_at": 1.0}, handle)

            app = types.SimpleNamespace()
            app.hass = DummyHass()
            app.ENTITY_MAP = {"switch": "switch.rd6018"}
            app.charge_controller = types.SimpleNamespace(is_active=False)
            app.manual_session_manager = None
            app._charge_notify = lambda *args, **kwargs: None

            guard = V2RuntimeSafetyGuard(app)
            guard.OFF_CONFIRMATION_WINDOW_S = 0.0
            guard.OFF_CONFIRMATION_POLL_S = 0.0
            lease = ResidualLease()
            guard.edge_safety_lease = lease
            guard.edge_lease_enforced = True
            app.runtime_safety_guard = guard

            manager = RdControlModeManager(app, state_file=mode_file)
            app.rd_control_mode_manager = manager
            self.assertTrue(manager.hands_off)

            d061 = types.SimpleNamespace(edge=None)
            coordinator = ManagedMixAdoptionCoordinator(
                app,
                manager,
                d061,
                state_file=f"{tmp}/mix.json",
                history_reader=object(),
            )
            app.rd_managed_mix_adoption = coordinator
            coordinator.state = ManagedMixState.ADOPTION_PENDING

            reason = (
                "MIX_ADOPTED_INCOMPLETE_AFTER_EDGE:RuntimeSafetyError:"
                "edge live adoption was not positively acknowledged"
            )
            with self.assertLogs("rd6018", level="INFO") as captured:
                ok = await coordinator.force_verified_off(reason, failed=True)

            self.assertTrue(ok)
            self.assertEqual(coordinator.state, ManagedMixState.FAILED)
            self.assertEqual(coordinator.terminal_reason, reason)
            self.assertEqual(app.hass.live["switch"], "off")
            self.assertEqual(app.hass.turn_off_calls, 1)
            self.assertEqual(app.hass.writes, [])
            self.assertEqual(lease.disarm_calls, 1)
            self.assertFalse(lease.armed)

            journal = "\n".join(captured.output)
            self.assertIn("Output OFF verified; edge lease disarm may proceed", journal)
            self.assertIn("Edge safety lease disarm confirmed", journal)


if __name__ == "__main__":
    unittest.main()
