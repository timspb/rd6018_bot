"""Source-local P3-1B physical wiring contracts.

These tests deliberately parse source instead of importing the production entrypoint:
importing bot.py composes the effectful production runtime at module scope.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _tree(relative: str) -> ast.Module:
    return ast.parse((ROOT / relative).read_text(encoding="utf-8"), filename=relative)


def _function(tree: ast.AST, name: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    matches = [
        node for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
    ]
    if len(matches) != 1:
        raise AssertionError(f"expected one function {name!r}, found {len(matches)}")
    return matches[0]


def _class(tree: ast.AST, name: str) -> ast.ClassDef:
    matches = [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef) and node.name == name]
    if len(matches) != 1:
        raise AssertionError(f"expected one class {name!r}, found {len(matches)}")
    return matches[0]


def _called_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def _calls(node: ast.AST, name: str) -> list[ast.Call]:
    return [item for item in ast.walk(node) if isinstance(item, ast.Call) and _called_name(item) == name]


def _definitions(node: ast.AST, name: str) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    return [item for item in ast.walk(node)
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == name]


def _is_attr(node: ast.AST, attr: str) -> bool:
    return isinstance(node, ast.Attribute) and node.attr == attr


class ModularizationPhysicalWiringTests(unittest.TestCase):
    def test_production_installs_safety_then_control_adoption_and_mix_wrappers(self):
        bot = _tree("bot.py")
        compose = _function(bot, "compose")
        ordered_installers = (
            "install_production",
            "install_rd_control_mode",
            "install_managed_live_adoption",
            "install_managed_mix_adoption",
        )
        lines = []
        for installer in ordered_installers:
            calls = _calls(compose, installer)
            self.assertTrue(calls, f"ProductionComposition.compose must call {installer}")
            lines.append(min(call.lineno for call in calls))
        self.assertEqual(lines, sorted(lines), "production wrapper installer order changed")

        bootstrap = _tree("production_bootstrap.py")
        install_production = _function(bootstrap, "install_production")
        self.assertTrue(_calls(install_production, "install_managed_runtime_safety"))

        managed_guard = _tree("runtime/safety/managed_guard.py")
        guard_class = _class(managed_guard, "ManagedRuntimeSafetyGuard")
        self.assertTrue(
            any(isinstance(base, ast.Name) and base.id == "StrictRuntimeSafetyGuard"
                for base in guard_class.bases),
            "managed guard must retain its strict/runtime safety ancestry",
        )
        guard_installer = _function(managed_guard, "install_managed_runtime_safety")
        self.assertTrue(
            any(isinstance(call.func, ast.Name) and call.func.id == "ManagedRuntimeSafetyGuard"
                for call in _calls(guard_installer, "ManagedRuntimeSafetyGuard")),
            "production safety installer no longer constructs ManagedRuntimeSafetyGuard",
        )

        # Actuation is not implemented as stacked HassClient monkeypatches.
        # Ownership/adoption/MIX policy converges at the single ExecutionPort.
        control = _function(_tree("rd_control_mode.py"), "install_rd_control_mode")
        self.assertTrue(_calls(control, "RdControlModeManager"))
        self.assertFalse(
            any(_definitions(control, method) for method in ("turn_on", "turn_off", "set_voltage", "set_current")),
            "control mode must not install a second physical writer layer",
        )
        adoption = _function(_tree("rd_managed_adoption.py"), "install_managed_live_adoption")
        self.assertTrue(_calls(adoption, "ManagedLiveAdoptionCoordinator"))
        mix_installer = _function(_tree("rd_managed_mix_adoption.py"), "install_managed_mix_adoption")
        self.assertTrue(_calls(mix_installer, "install_runtime_composition"))
        mix_composition = _function(_tree("rd_managed_mix.py"), "install_runtime_composition")
        self.assertFalse(
            any(_definitions(mix_composition, method) for method in ("turn_on", "turn_off", "set_voltage", "set_current")),
            "MIX policy must not monkeypatch physical writers",
        )

        execution = _tree("application/execution_port.py")
        port_class = _class(execution, "ExecutionPort")
        normal_gate = _function(port_class, "_normal_actuation_gate")
        gate_constants = {node.value for node in ast.walk(normal_gate)
                         if isinstance(node, ast.Constant) and isinstance(node.value, str)}
        for token in ("hands_off", "edge_autonomous", "release_in_progress", "managed_actuation_ready"):
            self.assertIn(token, gate_constants, f"central execution gate lost {token}")
        adopted_write = _function(port_class, "_authorize_adopted_write")
        self.assertTrue(any(isinstance(node, ast.Attribute) and node.attr == "authorize_managed_write"
                            for node in ast.walk(adopted_write)))

    def test_declared_entrypoint_composes_and_runs_the_same_production_runtime_module(self):
        bot = _tree("bot.py")
        runtime_imports = [
            node for node in bot.body
            if isinstance(node, ast.ImportFrom)
            and node.module == "runtime"
            and any(alias.name == "production_runtime" and alias.asname == "_runtime_substrate"
                    for alias in node.names)
        ]
        self.assertEqual(len(runtime_imports), 1, "bot.py must bind runtime.production_runtime")

        composition_assignments = [
            node for node in bot.body
            if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "_composition" for target in node.targets)
        ]
        self.assertEqual(len(composition_assignments), 1)
        value = composition_assignments[0].value
        self.assertIsInstance(value, ast.Call)
        self.assertEqual(_called_name(value), "compose")
        constructor = value.func.value
        self.assertIsInstance(constructor, ast.Call)
        self.assertEqual(_called_name(constructor), "ProductionComposition")
        self.assertTrue(constructor.args and isinstance(constructor.args[0], ast.Name))
        self.assertEqual(constructor.args[0].id, "_runtime_substrate")

        main = _function(bot, "main")
        run_calls = [call for call in _calls(main, "run") if _is_attr(call.func, "run")]
        self.assertEqual(len(run_calls), 1)
        self.assertIsInstance(run_calls[0].func.value, ast.Name)
        self.assertEqual(run_calls[0].func.value.id, "_composition")

    def test_operator_pause_physical_writes_use_execution_port_and_gate_clock_clear_on_on_result(self):
        tree = _tree("application/operator_pause_use_case.py")
        use_cases = [
            _function(tree, "toggle_operator_pause"),
            _function(tree, "_toggle_operator_pause_locked"),
        ]
        use_case = use_cases[1]
        forbidden = {"turn_on", "turn_off", "set_voltage", "set_current"}
        direct_hass_writes = [
            call for use_case in use_cases for call in ast.walk(use_case)
            if isinstance(call, ast.Call)
            and isinstance(call.func, ast.Attribute)
            and call.func.attr in forbidden
            and isinstance(call.func.value, ast.Attribute)
            and call.func.value.attr == "hass"
        ]
        self.assertEqual(direct_hass_writes, [], "operator pause must not write through host.hass")

        port_write_calls = [
            call for use_case in use_cases for call in ast.walk(use_case)
            if isinstance(call, ast.Call)
            and isinstance(call.func, ast.Attribute)
            and call.func.attr in {"request_verified_off", "request_verified_on", "program_voltage", "program_current"}
        ]
        self.assertTrue(port_write_calls, "pause use case must retain physical operations")
        for call in port_write_calls:
            receiver = call.func.value
            self.assertIsInstance(receiver, ast.Name)
            self.assertEqual(receiver.id, "port")

        enabled_assignments = [
            node for node in ast.walk(use_case)
            if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "enabled" for target in node.targets)
        ]
        self.assertEqual(len(enabled_assignments), 1)
        self.assertGreaterEqual(enabled_assignments[0].lineno, max(call.lineno for call in port_write_calls
                                                                    if call.func.attr == "request_verified_on"))
        denied_on_check = [
            node for node in ast.walk(use_case)
            if isinstance(node, ast.If)
            and isinstance(node.test, ast.UnaryOp)
            and isinstance(node.test.op, ast.Not)
            and isinstance(node.test.operand, ast.Name)
            and node.test.operand.id == "enabled"
        ]
        self.assertEqual(len(denied_on_check), 1)
        # The SAFE_WAIT success path legitimately shifts/clears before the
        # re-enable branch. Check the post-ON occurrences specifically.
        clock_shifts = [call for call in _calls(use_case, "shift_active_clocks")
                        if call.lineno > denied_on_check[0].lineno]
        clears = [call for call in _calls(use_case, "_clear_operator_pause")
                  if call.lineno > denied_on_check[0].lineno]
        self.assertTrue(clock_shifts and clears)
        self.assertTrue(any(isinstance(stmt, ast.Return) for stmt in denied_on_check[0].body),
                        "failed verified ON must return before clock shift and pause clear")

    def test_runtime_pause_branch_uses_verified_off_transaction_only(self):
        runtime = _tree("runtime/production_runtime.py")
        # The pause containment block belongs to the long-running data_logger,
        # not the separate low-rate charge_monitor telemetry alert task.
        monitor = _function(runtime, "data_logger")
        pause_branches = [
            node for node in ast.walk(monitor)
            if isinstance(node, ast.If)
            and isinstance(node.test, ast.Call)
            and _called_name(node.test) == "_operator_pause_active"
        ]
        self.assertEqual(len(pause_branches), 1, "charge monitor pause branch moved or became ambiguous")
        pause_branch = pause_branches[0]
        output_on_branches = [
            node for node in ast.walk(pause_branch)
            if isinstance(node, ast.If)
            and isinstance(node.test, ast.Name)
            and node.test.id == "output_on"
        ]
        self.assertEqual(len(output_on_branches), 1)
        off_transactions = [
            call for call in _calls(output_on_branches[0], "request_verified_off")
            if isinstance(call.func, ast.Attribute)
        ]
        self.assertEqual(len(off_transactions), 1,
                         "paused Output containment must request the established verified-OFF transaction")

        direct_hass_writes = [
            call for call in ast.walk(monitor)
            if isinstance(call, ast.Call)
            and isinstance(call.func, ast.Attribute)
            and call.func.attr in {"turn_on", "turn_off", "set_voltage", "set_current"}
            and (
                (isinstance(call.func.value, ast.Attribute) and call.func.value.attr == "hass")
                or (isinstance(call.func.value, ast.Name) and call.func.value.id == "hass")
            )
        ]
        self.assertEqual(direct_hass_writes, [], "production runtime must not directly call physical HassClient writers")


if __name__ == "__main__":
    unittest.main()
