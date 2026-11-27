"""P5-9A source and fake-only contracts for adopted MIX composition.

These tests pin source wiring and local wrapper behavior. They do not prove that
the production composition is reachable in a running or deployed process.
"""

from __future__ import annotations

import ast
import asyncio
from enum import Enum
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock


ROOT = Path(__file__).resolve().parents[1]


class _MixState(str, Enum):
    ACTIVE = "active"
    OFF_PENDING = "off_pending"
    FAILED = "failed"


def _tree(name: str) -> ast.Module:
    return ast.parse((ROOT / name).read_text(encoding="utf-8"), filename=name)


def _function(tree: ast.AST, name: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    found = [n for n in ast.walk(tree)
             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name]
    if len(found) != 1:
        raise AssertionError(f"expected one {name}, found {len(found)}")
    return found[0]


def _execute_function(tree: ast.AST, name: str, namespace: dict):
    fn = _function(tree, name)
    module = ast.Module(body=[fn], type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), "source-contract", "exec"), namespace)
    return namespace[name]


def _mix_source() -> ast.Module:
    return _tree("rd_managed_mix.py")


class AdoptedMixBoundaryTests(unittest.TestCase):
    def test_runtime_composition_does_not_monkeypatch_hass_actuators(self):
        source = (ROOT / "rd_managed_mix.py").read_text(encoding="utf-8")
        for token in (
            "hass.turn_on =",
            "hass.set_voltage =",
            "hass.set_current =",
            "_d062_managed_mix_wrapped",
        ):
            self.assertNotIn(token, source)

    def test_mix_authority_is_owned_by_execution_port(self):
        source = (ROOT / "application" / "execution_port.py").read_text(encoding="utf-8")
        self.assertIn('getattr(app, "rd_managed_mix_adoption", None)', source)
        self.assertIn('mix.authorize_managed_write(field, value)', source)
        self.assertIn('mix.ratchet_after_managed_write(field, value)', source)
        self.assertIn('"MIX_ADOPTED cannot re-energize Output', source)

    def test_runtime_composition_keeps_controller_hooks_but_not_transport_wrappers(self):
        node = _function(_tree("rd_managed_mix.py"), "install_runtime_composition")
        attrs = {
            n.attr
            for n in ast.walk(node)
            if isinstance(n, ast.Attribute)
        }
        self.assertIn("_d062_managed_mix_hooks", attrs)
        self.assertNotIn("_d062_managed_mix_wrapped", attrs)

    def test_d062_ui_projection_is_app_scoped_and_does_not_replace_hmi_callbacks(self):
        source = _tree("rd_managed_mix_adoption.py")
        names = {n.name for n in source.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        self.assertNotIn("_install_hmi_composition", names)
        for node in ast.walk(source):
            if isinstance(node, ast.Assign):
                self.assertFalse(any(isinstance(target, ast.Attribute) and target.attr in {
                    "build_operator_hmi_state", "build_operator_keyboard", "render_operator_details", "_more_keyboard"
                } for target in node.targets))
        state = (ROOT / "runtime/ui/components/hmi_state.py").read_text(encoding="utf-8")
        keyboard = (ROOT / "runtime/ui/components/hmi_action_keyboard.py").read_text(encoding="utf-8")
        details = (ROOT / "runtime/ui/components/hmi_operator_details.py").read_text(encoding="utf-8")
        self.assertIn('getattr(app, "rd_managed_mix_adoption", None)', state)
        self.assertIn('getattr(app, "rd_managed_mix_adoption", None)', keyboard)
        self.assertIn('getattr(app, "rd_managed_mix_adoption", None)', details)

    def test_adoption_preconditions_precede_edge_command_invocation(self):
        adopt = _function(_tree("rd_managed_mix.py"), "adopt")
        calls = [n for n in ast.walk(adopt) if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Attribute) and n.func.attr == "adopt"]
        self.assertEqual(len(calls), 1)
        edge_call = calls[0]
        source = (ROOT / "rd_managed_mix.py").read_text(encoding="utf-8")
        source_lines = source.splitlines()
        fn_start = adopt.lineno - 1
        prefix = "\n".join(source_lines[fn_start:edge_call.lineno - 1])
        for required in ('getattr(self.manager, "hands_off"', 'getattr(self.guard, "_off_unconfirmed"',
                         "self._conflict()", "self._require_budget", "self.edge.prepare()",
                         "self._preflight_mix_live("):
            self.assertIn(required, prefix)
        self.assertIn("edge_command_uncertain = bool(", "\n".join(source_lines[edge_call.lineno:]))

    def test_install_module_constructs_coordinator_once_and_delegates_runtime_install(self):
        installer = _function(_tree("rd_managed_mix.py"), "install_runtime_composition")
        self.assertFalse(any(isinstance(n, ast.Attribute) and n.attr == "_d062_managed_mix_wrapped"
                             for n in ast.walk(installer)))
        self.assertTrue(any(isinstance(n, ast.Attribute) and n.attr == "_d062_managed_mix_hooks"
                            for n in ast.walk(installer)))
        owner = _function(_tree("rd_managed_mix_adoption.py"), "install_managed_mix_adoption")
        self.assertTrue(any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                            and n.func.id == "ManagedMixAdoptionCoordinator" for n in ast.walk(owner)))
        self.assertTrue(any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                            and n.func.id == "install_runtime_composition" for n in ast.walk(owner)))

    def test_bot_production_composition_wires_d061_into_d062_and_exposes_coordinator(self):
        bot = _tree("bot.py")
        composition = next(n for n in ast.walk(bot) if isinstance(n, ast.ClassDef)
                           and n.name == "ProductionComposition")
        calls = [n for n in ast.walk(composition) if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Name) and n.func.id == "install_managed_mix_adoption"]
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(calls[0].args), 3)
        self.assertIsInstance(calls[0].args[2], ast.Name)
        self.assertEqual(calls[0].args[2].id, "_rd_managed_live_adoption")
        self.assertTrue(any(isinstance(n, ast.Assign) and any(isinstance(t, ast.Attribute)
                            and t.attr == "rd_managed_mix_adoption" for t in n.targets)
                            for n in ast.walk(composition)))

    def test_force_verified_off_uses_existing_off_owner_and_requires_positive_result(self):
        async def exercise():
            coordinator = SimpleNamespace()
            coordinator.manager = SimpleNamespace(hands_off=False)
            coordinator.app = SimpleNamespace()
            coordinator.guard = SimpleNamespace()
            coordinator.state = _MixState.ACTIVE
            coordinator.terminal_reason = ""
            coordinator.finish_hold_started_at_s = None
            coordinator._finish_hold_anchor_mono = None
            coordinator._active_anchor_mono = None
            coordinator.last_status = ""
            coordinator._advance_active_clock = lambda: None
            coordinator._persist = lambda: None
            port = SimpleNamespace(request_emergency_off=AsyncMock(return_value=False))
            off = _execute_function(_mix_source(), "force_verified_off", {
                "Any": object,
                "get_or_create_execution_port": lambda app: port,
                "ManagedMixState": _MixState,
            })
            coordinator.force_verified_off = lambda *a, **kw: off(coordinator, *a, **kw)
            result = await coordinator.force_verified_off("CONTRACT")
            self.assertFalse(result)
            self.assertIs(coordinator.state, _MixState.OFF_PENDING)
            port.request_emergency_off.assert_awaited_once_with()
            coordinator.manager.hands_off = True
            coordinator.manager.operator_output_off = AsyncMock(return_value=True)
            coordinator.app.ENTITY_MAP = {"switch": "switch.rd"}
            result = await coordinator.force_verified_off("CONTRACT")
            self.assertTrue(result)
            self.assertIs(coordinator.state, _MixState.FAILED)
            coordinator.manager.operator_output_off.assert_awaited_once_with("switch.rd")
        asyncio.run(exercise())


if __name__ == "__main__":
    unittest.main()
