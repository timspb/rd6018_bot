from __future__ import annotations

import ast
import inspect
import unittest
from pathlib import Path

from runtime.charge.runtime import residual_terminal as owner


ROOT = Path(__file__).resolve().parents[1]


class ResidualTerminalDecisionTests(unittest.TestCase):
    def test_idle_and_done_keep_distinct_return_semantics(self):
        idle = owner.decide_residual_terminal("IDLE", idle_stage="IDLE", done_stage="DONE")
        done = owner.decide_residual_terminal("DONE", idle_stage="IDLE", done_stage="DONE")
        self.assertTrue(idle.return_after_observation)
        self.assertFalse(done.return_after_observation)

    def test_nonterminal_and_unknown_stages_are_rejected(self):
        for stage in ("PREP", "COOLING", "UNKNOWN"):
            with self.subTest(stage=stage), self.assertRaises(ValueError):
                owner.decide_residual_terminal(stage, idle_stage="IDLE", done_stage="DONE")

    def test_residual_scaffold_routes_terminal_policy_through_single_owner(self):
        source = (ROOT / "runtime/charge/runtime/residual_scaffold.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Name) and node.func.id == "decide_residual_terminal"]
        self.assertEqual(len(calls), 1)
        self.assertIn("terminal.return_after_observation", source)
        self.assertIn("DONE has no automatic transition", source)
        owner_source = inspect.getsource(owner)
        owner_tree = ast.parse(owner_source)
        setters = [node.func.attr for node in ast.walk(owner_tree)
                   if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)]
        self.assertFalse(set(setters) & {"set_voltage", "set_current", "set_ovp", "set_ocp", "turn_on", "turn_off"})
        self.assertNotIn("execution_port", owner_source)


if __name__ == "__main__":
    unittest.main()
