"""Source-level barriers for D123 Sprint 58 guarded activation."""
import ast
import textwrap
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


def source(path):
    return (ROOT / path).read_text(encoding="utf-8")


class Sprint58GuardedActivationArchitectureTests(unittest.TestCase):
    def test_single_canonical_restore_and_guard_parser_implementations(self):
        persistence = ast.parse(source("runtime/charge/persistence.py"))
        guard_session = ast.parse(source("runtime/charge/strategy/main_guard_session.py"))
        self.assertEqual(sum(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                             and n.name == "restore_session" for n in ast.walk(persistence)), 1)
        self.assertEqual(sum(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                             and n.name == "read_guard" for n in ast.walk(guard_session)), 1)

    def test_activation_path_has_no_hardware_writer_and_reuses_existing_owner(self):
        startup_text = source("runtime/startup_recovery.py")
        forbidden = {"request_verified_on", "turn_on", "safe_enable_output", "program_voltage",
                     "program_current", "program_ocp", "program_ovp"}
        activation = startup_text.split("if candidate is not None:", 1)[1].split("live = await app.hass.get_all_live()", 1)[0]
        startup = ast.parse(textwrap.dedent(activation))
        invoked = {node.func.attr for node in ast.walk(startup)
                   if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}
        self.assertFalse(invoked & forbidden)
        self.assertIn("read_guard", source("runtime/startup_recovery.py"))
        self.assertIn("assess_main_guard_before_output_on", source("runtime/startup_recovery.py"))
        self.assertIn("_guard_owner_lock", source("runtime/startup_recovery.py"))
        self.assertIn("restore_session(", source("charge_controller.py"))

    def test_verified_on_paths_are_held_until_separate_resume_gate(self):
        port = source("application/execution_port.py")
        enable = port.split("async def enable(", 1)[1].split("async def apply_intent(", 1)[0]
        request_on = port.split("async def request_verified_on(", 1)[1].split("async def program_voltage(", 1)[0]
        self.assertIn("guarded_restore_activated_off", enable)
        self.assertIn("guarded_restore_activated_off", request_on)
        self.assertIn("execution_owner.turn_on()", request_on)

    def test_emergency_off_remains_independent_of_activation_latch(self):
        port = source("application/execution_port.py")
        off = port.split("async def request_verified_off(", 1)[1].split("async def request_verified_off_evidence(", 1)[0]
        self.assertIn("execution_owner.turn_off()", off)
        self.assertNotIn("guarded_restore_activated_off", off)

    def test_activated_off_session_skips_background_charge_tick(self):
        import asyncio
        from types import SimpleNamespace
        from application.charge_session_tick import run_charge_session_tick

        host = SimpleNamespace(_guarded_restore_activated_off=True, last_update_time=0.0)
        actions = asyncio.run(run_charge_session_tick(host, 0, 0, None, False, 0))
        self.assertEqual(actions, {})
        self.assertGreater(host.last_update_time, 0.0)

    def test_activation_adds_only_a_permit_value_not_a_second_state_owner(self):
        session = ast.parse(source("runtime/charge/session.py"))
        names = {node.name for node in ast.walk(session) if isinstance(node, ast.ClassDef)}
        self.assertIn("GuardedRestoreActivationPermit", names)
        self.assertNotIn("GuardedRestoreManager", names)
        self.assertNotIn("GuardedRestoreJournal", names)
        self.assertEqual(source("runtime/charge/persistence.py").count("def restore_session("), 1)

    def test_sprint59_has_one_receipt_gated_latch_clear_and_no_startup_writer(self):
        port_text = source("application/execution_port.py")
        tree = ast.parse(port_text)
        execution = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "ExecutionPort")
        method = next(n for n in execution.body if isinstance(n, ast.AsyncFunctionDef)
                      and n.name == "execute_guarded_physical_resume")
        clears = [n for n in ast.walk(method) if isinstance(n, ast.Assign)
                  and any(isinstance(t, ast.Attribute) and t.attr == "_guarded_restore_activated_off"
                          for t in n.targets)
                  and isinstance(n.value, ast.Constant) and n.value.value is False]
        # One commit block updates the port and mirrored canonical controller
        # latch atomically after receipt.
        self.assertEqual(len(clears), 2)
        startup = ast.parse(source("runtime/startup_recovery.py"))
        resume = next(n for n in startup.body if isinstance(n, ast.ClassDef) and n.name == "StartupRecovery")
        method = next(n for n in resume.body if isinstance(n, ast.AsyncFunctionDef)
                      and n.name == "guarded_physical_resume")
        calls = {n.func.attr for n in ast.walk(method) if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Attribute)}
        names = {n.func.id for n in ast.walk(method) if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Name)}
        self.assertIn("get_native_guard_pre_on_snapshot", source("runtime/startup_recovery.py"))
        self.assertIn("assess_main_guard_before_output_on", names)
        self.assertFalse({"turn_on", "safe_enable_output", "program_current", "program_voltage"} & calls)
        self.assertIn("READY_BUT_NOT_EXECUTED", port_text)
        self.assertIn("VERIFIED_ON_COMMITTED", port_text)

    def test_resume_assessment_has_no_persistence_write_or_ha_aggregate_authority(self):
        method = source("runtime/startup_recovery.py").split("async def guarded_physical_resume", 1)[1]
        self.assertNotIn("write_session", method)
        self.assertNotIn("save_session", method)
        self.assertNotIn("get_all_live", method)
        self.assertIn("get_native_guard_pre_on_snapshot", method)


if __name__ == "__main__":
    unittest.main()
