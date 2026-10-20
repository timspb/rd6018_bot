"""Static ownership gates for the application-owned charge tick route."""

import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


def _calls(tree, names):
    return [node for node in ast.walk(tree) if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name) and node.func.id in names]


class ApplicationTickOwnershipTests(unittest.TestCase):
    def test_controller_tick_is_a_single_application_handoff(self):
        tree = ast.parse((ROOT / "charge_controller.py").read_text(encoding="utf-8"))
        cls = next(node for node in tree.body if isinstance(node, ast.ClassDef)
                   and node.name == "ManagedChargeController")
        tick = next(node for node in cls.body if isinstance(node, ast.AsyncFunctionDef)
                    and node.name == "tick")
        handoffs = _calls(tick, {"run_charge_session_tick"})
        self.assertEqual(len(handoffs), 1)
        self.assertEqual(_calls(tick, {
            "run_charge_stage_tick", "apply_authoritative_stage_tick",
            "build_signal_context", "build_trace_point_metadata",
            "build_shadow_metadata", "log_analysis_events",
        }), [])
        for method_name in ("_apply_authoritative_decision", "_enter_desulfation", "_enter_mix"):
            self.assertNotIn(method_name, {node.name for node in cls.body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))})
        for method_name in ("_is_authoritative_stage", "_apply_stage_authority"):
            self.assertNotIn(method_name, {node.name for node in cls.body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))})

    def test_diagnostic_and_mix_subclasses_have_no_stage_router_overrides(self):
        for path, class_name in (
            ("diagnostic_controller.py", "DiagnosticProductionChargeController"),
            ("mix_active_authority.py", "MixActiveAuthorityMixin"),
        ):
            tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
            cls = next(node for node in tree.body
                       if isinstance(node, ast.ClassDef) and node.name == class_name)
            names = {node.name for node in cls.body
                     if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
            self.assertNotIn("_apply_stage_authority", names)
            if class_name == "MixActiveAuthorityMixin":
                self.assertNotIn("tick", names)

        app = ast.parse((ROOT / "application/charge_stage_tick.py").read_text(encoding="utf-8"))
        apply = next(node for node in app.body if isinstance(node, ast.FunctionDef)
                     and node.name == "apply_charge_stage_authority")
        self.assertEqual(len(_calls(app, {"apply_authoritative_stage_tick"})), 1)
        self.assertEqual(_calls(app, {
            "set_voltage", "set_current", "set_ovp", "set_ocp", "turn_on",
            "turn_off", "safe_enable_output",
        }), [])

    def test_application_tick_routes_through_stage_owner_and_has_no_physical_writer(self):
        session = ast.parse((ROOT / "application/charge_session_tick.py").read_text(encoding="utf-8"))
        tick = next(node for node in session.body if isinstance(node, ast.AsyncFunctionDef)
                    and node.name == "run_charge_session_tick")
        body = next(node for node in session.body if isinstance(node, ast.AsyncFunctionDef)
                    and node.name == "_run_charge_session_tick_body")
        self.assertEqual(len(_calls(body, {"run_charge_stage_tick"})), 1)
        self.assertEqual(_calls(tick, {
            "set_voltage", "set_current", "set_ovp", "set_ocp", "turn_on",
            "turn_off", "safe_enable_output", "execute_controller_actions",
        }), [])
        router = ast.parse((ROOT / "application/charge_stage_tick.py").read_text(encoding="utf-8"))
        self.assertEqual(len(_calls(router, {
            "run_authoritative_main_scaffold", "run_authoritative_mix_scaffold",
            "run_authoritative_recovery_scaffold", "run_authoritative_residual_scaffold",
        })), 4)
        self.assertEqual(_calls(router, {
            "set_voltage", "set_current", "set_ovp", "set_ocp", "turn_on",
            "turn_off", "safe_enable_output",
        }), [])


if __name__ == "__main__":
    unittest.main()
