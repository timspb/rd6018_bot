from pathlib import Path
import unittest


class AutonomousStartupAuthorityContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = Path("bot.py").read_text(encoding="utf-8")
        cls.gate = Path("rd_startup_authority.py").read_text(encoding="utf-8")

    def test_final_startup_gate_is_installed_after_runtime_composition(self):
        ownership = self.text.index("install_rd_control_mode(_legacy")
        managed_mix = self.text.index("install_managed_mix_adoption(")
        startup = self.text.index("install_rd_startup_authority_gate(")
        self.assertLess(ownership, managed_mix)
        self.assertLess(managed_mix, startup)

    def test_managed_recovery_is_inside_explicit_reconciliation_task(self):
        reconcile = self.text.index("reconcile_startup_authority(")
        mix_recovery = self.text.index("await _rd_managed_mix_adoption.recover_startup()")
        live_recovery = self.text.index("await _rd_managed_live_adoption.recover_startup()")
        diagnostic_recovery = self.text.index("await recover_diagnostic_persistence(_legacy)")
        self.assertLess(mix_recovery, reconcile)
        self.assertLess(live_recovery, reconcile)
        self.assertLess(diagnostic_recovery, reconcile)
        self.assertIn("if not await _rd_managed_mix_adoption.recover_startup():", self.text)
        self.assertIn("if not await _rd_managed_live_adoption.recover_startup():", self.text)

    def test_unknown_edge_authority_retries_read_only_and_never_opens_control(self):
        self.assertIn("candidate = self.parse_explicit(raw)", self.gate)
        self.assertIn("if candidate is None:", self.gate)
        self.assertIn("await asyncio.sleep(delay)", self.gate)
        self.assertIn("if not self.recovery_scope and not self.managed_actuation_ready", self.gate)

    def test_autonomous_skips_managed_recovery(self):
        block = self.gate.split("async def reconcile(", 1)[1]
        autonomous = block.index("if candidate:")
        recovery = block.index("recovered = bool(await recover())")
        self.assertLess(autonomous, recovery)
        self.assertIn('return "autonomous"', block[autonomous:recovery])

    def test_recovery_has_narrow_task_local_actuator_scope(self):
        self.assertIn("contextvars.ContextVar", self.gate)
        self.assertIn("token = self._recovery_scope.set(True)", self.gate)
        self.assertIn("self._recovery_scope.reset(token)", self.gate)
        self.assertIn("if not self.recovery_scope and not self.managed_actuation_ready", self.gate)

    def test_failed_recovery_is_throttled_and_rechecks_edge_authority(self):
        block = self.gate.split("recovered = bool(await recover())", 1)[1]
        failure_block = block.split("self.mark_managed_recovered()", 1)[0]
        self.assertIn("await asyncio.sleep(managed_retry_delay)", failure_block)
        self.assertIn("continue", failure_block)
        self.assertNotIn('return "blocked"', failure_block)
        self.assertIn("managed_retry_delay = max(delay, float(recovery_retry_s))", self.gate)

    def test_deferred_restore_is_replayed_only_after_managed_authority(self):
        self.assertIn("self._deferred_restore_requested = True", self.gate)
        coordinator = self.gate.split("async def reconcile_startup_authority(", 1)[1]
        self.assertIn('if result != "managed" or not gate.deferred_restore_requested:', coordinator)
        self.assertIn("if not gate.managed_actuation_ready:", coordinator)
        self.assertIn("await replay_deferred_restore()", coordinator)
        self.assertIn("gate.take_deferred_restore_request()", coordinator)
        self.assertIn("gate.discard_deferred_restore_request()", self.gate)

    def test_deferred_restore_uses_fresh_live_and_composed_safe_actuation(self):
        replay = self.text.split("async def _replay_deferred_startup_restore()", 1)[1]
        replay = replay.split("async def main()", 1)[0]
        self.assertIn("live = await _legacy.hass.get_all_live()", replay)
        self.assertIn("controller.try_restore_session(", replay)
        self.assertIn("_legacy._apply_restore_time_corrections(controller, live)", replay)
        self.assertIn("_legacy._operator_pause_active()", replay)
        self.assertIn("_legacy._restore_allows_auto_enable(controller)", replay)

        # D-STARTUP-3 deliberately realizes an eligible restored MANAGED session only
        # after startup reconciliation. The calls must go through the final composed
        # HassClient/runtime-safety surface; raw actuator aliases would bypass the gate.
        self.assertIn("await _legacy._apply_phase_protection(uv, ui)", replay)
        self.assertIn("await _legacy.hass.set_voltage(uv)", replay)
        self.assertIn("await _legacy.hass.set_current(_legacy._cap_current(ui))", replay)
        self.assertIn("await _legacy.hass.turn_on(_legacy.ENTITY_MAP[\"switch\"])", replay)
        self.assertIn("await _legacy.hass.turn_off(_legacy.ENTITY_MAP[\"switch\"])", replay)
        self.assertNotIn("_raw_turn_on", replay)
        self.assertNotIn("_raw_turn_off", replay)
        self.assertNotIn("_raw_set_voltage", replay)
        self.assertNotIn("_raw_set_current", replay)


if __name__ == "__main__":
    unittest.main()
