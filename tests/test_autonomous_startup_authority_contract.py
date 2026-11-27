from pathlib import Path
import ast
import unittest


class AutonomousStartupAuthorityContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = Path("bot.py").read_text(encoding="utf-8")
        cls.recovery = Path("runtime/startup_recovery.py").read_text(encoding="utf-8")
        cls.lifecycle = Path("runtime/production_lifecycle.py").read_text(encoding="utf-8")
        cls.gate = Path("rd_startup_authority.py").read_text(encoding="utf-8")
        cls.execution = Path("application/execution_port.py").read_text(encoding="utf-8")

    def test_both_process_startup_paths_apply_cold_start_policy_without_on_in_that_branch(self):
        for source, class_name, method_name in (
            (self.lifecycle, "ProductionRuntimeLifecycle", "run"),
            (self.recovery, "StartupRecovery", "replay_deferred_startup_restore"),
        ):
            module = ast.parse(source)
            cls = next(node for node in module.body
                       if isinstance(node, ast.ClassDef) and node.name == class_name)
            method = next(node for node in cls.body
                          if isinstance(node, ast.AsyncFunctionDef) and node.name == method_name)
            policy_calls = [node for node in ast.walk(method)
                            if isinstance(node, ast.Call)
                            and ast.unparse(node.func) == "RecoveryAuthorizationInput"
                            and any(keyword.arg == "cold_start"
                                    and isinstance(keyword.value, ast.Constant)
                                    and keyword.value.value is True
                                    for keyword in node.keywords)]
            self.assertEqual(len(policy_calls), 1, method_name)
            containing_branches = [node for node in ast.walk(method)
                                   if isinstance(node, ast.If)
                                   and any(candidate is policy_calls[0]
                                           for candidate in ast.walk(node))]
            branch = (min(containing_branches,
                          key=lambda node: sum(1 for _ in ast.walk(node)))
                      if containing_branches else method)
            calls = {ast.unparse(node.func) for node in ast.walk(branch)
                     if isinstance(node, ast.Call)}
            self.assertIn("authorize_recovery_action", calls, method_name)
            self.assertIn("RecoveryAction.SKIP", source, method_name)
            self.assertNotIn("execution_port.request_verified_on", calls, method_name)
            self.assertNotIn("execution_port.program_voltage", calls, method_name)
            self.assertNotIn("execution_port.program_current", calls, method_name)

    def test_final_startup_gate_is_installed_after_runtime_composition(self):
        ownership = self.text.index("install_rd_control_mode(app")
        managed_mix = self.text.index("install_managed_mix_adoption(")
        startup = self.text.index("install_rd_startup_authority_gate(")
        self.assertLess(ownership, managed_mix)
        self.assertLess(managed_mix, startup)

    def test_managed_recovery_is_inside_explicit_reconciliation_task(self):
        reconcile = self.text.index("reconcile_startup_authority(")
        mix_recovery = self.recovery.index("await self.managed_mix.recover_startup()")
        live_recovery = self.recovery.index("await self.managed_live.recover_startup()")
        diagnostic_recovery = self.recovery.index("await recover_diagnostic_persistence(self.app)")
        self.assertLess(mix_recovery, reconcile)
        self.assertLess(live_recovery, reconcile)
        self.assertLess(diagnostic_recovery, reconcile)
        self.assertIn("if not await self.managed_mix.recover_startup():", self.recovery)
        self.assertIn("if not await self.managed_live.recover_startup():", self.recovery)

    def test_unknown_edge_authority_retries_read_only_and_never_opens_control(self):
        self.assertIn("candidate = self.parse_explicit(raw)", self.gate)
        self.assertIn("if candidate is None:", self.gate)
        self.assertIn("await asyncio.sleep(delay)", self.gate)
        self.assertIn("if startup is None or bool(getattr(startup, \"recovery_scope\", False))", self.execution)
        self.assertIn("if bool(getattr(startup, \"managed_actuation_ready\", True))", self.execution)

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
        manager_gate = self.execution.index("if manager is not None:")
        recovery_scope_gate = self.execution.index("if startup is None or bool(getattr(startup, \"recovery_scope\", False))")
        self.assertLess(manager_gate, recovery_scope_gate)
        self.assertIn("if bool(getattr(startup, \"managed_actuation_ready\", True))", self.execution)

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
        replay = self.recovery.split("async def replay_deferred_startup_restore(self)", 1)[1]
        replay = replay.split("\n    @_serialized_deferred_restore\n    async def guarded_physical_resume", 1)[0]
        self.assertIn("live = await execution_port.read_live()", replay)
        self.assertIn("controller.try_restore_session(", replay)
        self.assertIn("app._apply_restore_time_corrections(controller, live)", replay)
        self.assertIn("app._operator_pause_active()", replay)
        self.assertIn("app._restore_allows_auto_enable(controller)", replay)

        # Deferred restore is startup-only: the shared policy must deny the
        # generic automatic re-energization after a cold start.
        self.assertIn("execution_port = get_or_create_execution_port(app)", replay)
        self.assertIn("authorize_recovery_action(RecoveryAuthorizationInput(", replay)
        self.assertIn("cold_start=True", replay)
        self.assertIn("RecoveryAction.SKIP", replay)
        self.assertNotIn("request_verified_on", replay)
        self.assertNotIn("program_voltage", replay)
        self.assertNotIn("program_current", replay)
        self.assertNotIn("_apply_phase_protection", replay)
        self.assertIn("request_verified_off", replay)  # SAFE_WAIT remains OFF-only.
        self.assertIn("await execution_port.request_verified_off()", replay)
        for token in (
            "app.hass.set_voltage(",
            "app.hass.set_current(",
            "app.hass.turn_on(",
            "app.hass.turn_off(",
            "_raw_turn_on",
            "_raw_turn_off",
            "_raw_set_voltage",
            "_raw_set_current",
        ):
            self.assertNotIn(token, replay)


if __name__ == "__main__":
    unittest.main()
