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


if __name__ == "__main__":
    unittest.main()
