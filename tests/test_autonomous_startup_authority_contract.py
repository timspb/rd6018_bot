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
        reconcile = self.text.index("_rd_startup_authority.reconcile(")
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

    def test_failed_recovery_is_not_retried_into_an_off_storm(self):
        block = self.gate.split("recovered = bool(await recover())", 1)[1]
        self.assertIn('return "blocked"', block)
        # The retry loop exists only before recovery while authority itself is unknown.
        failure_block = block.split("self.mark_managed_recovered()", 1)[0]
        self.assertNotIn("await asyncio.sleep", failure_block)


if __name__ == "__main__":
    unittest.main()
