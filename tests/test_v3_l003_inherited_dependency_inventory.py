from __future__ import annotations

import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
V2_PATH = ROOT / "charge_controller_v2.py"
LEGACY_PATH = ROOT / "charge_logic.py"

EXPECTED_HISTORICAL_SUPPORT_CLOSURE = {
    "__init__",
    "_add_desulf_limits",
    "_add_phase_limits",
    "_apply_temperature_compensation",
    "_clear_restored_targets",
    "_clear_session_file",
    "_get_profile_target_v_i",
    "_get_stage_max_hours",
    "_get_target_finish_time",
    "_get_target_v_i",
    "_init_session",
    "_main_target",
    "_make_log_event_end",
    "_post_charge_profile_params",
    "_prep_target",
    "_record_safe_wait_sample",
    "_reset_bank_fault_state",
    "_reset_delta_and_blanking",
    "_reset_link_loss_state",
    "_reset_stage_metrics",
    "_save_session",
    "_session_rules_summary",
    "_temperature_compensation_coeff",
    "_temperature_compensation_delta",
    "reset_session_data",
    "start",
    "start_custom",
    "stop",
    "try_restore_session",
}


def _class(tree: ast.Module, name: str) -> ast.ClassDef:
    return next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == name
    )


def _methods(node: ast.ClassDef) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    return {
        item.name: item
        for item in node.body
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _self_calls(node: ast.AST) -> set[str]:
    result: set[str] = set()
    for item in ast.walk(node):
        if not isinstance(item, ast.Call):
            continue
        func = item.func
        if (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id == "self"
        ):
            result.add(func.attr)
    return result


def _super_calls(node: ast.AST) -> set[str]:
    result: set[str] = set()
    for item in ast.walk(node):
        if not isinstance(item, ast.Call):
            continue
        func = item.func
        if not isinstance(func, ast.Attribute):
            continue
        owner = func.value
        if (
            isinstance(owner, ast.Call)
            and isinstance(owner.func, ast.Name)
            and owner.func.id == "super"
        ):
            result.add(func.attr)
    return result


class L003InheritedDependencyInventoryTests(unittest.TestCase):
    def test_exact_historical_support_closure_is_bounded_and_tick_free(self) -> None:
        v2_tree = ast.parse(V2_PATH.read_text(encoding="utf-8"))
        legacy_tree = ast.parse(LEGACY_PATH.read_text(encoding="utf-8"))
        v2 = _class(v2_tree, "ChargeControllerV2")
        legacy = _class(legacy_tree, "ChargeController")

        self.assertEqual(
            [base.id for base in v2.bases if isinstance(base, ast.Name)],
            ["ChargeController"],
        )

        v2_methods = _methods(v2)
        legacy_methods = _methods(legacy)

        roots = _super_calls(v2)
        for method in v2_methods.values():
            roots.update(
                name
                for name in _self_calls(method)
                if name in legacy_methods and name not in v2_methods
            )

        closure: set[str] = set()
        pending = list(roots)
        while pending:
            name = pending.pop()
            if name in closure or name not in legacy_methods:
                continue
            closure.add(name)
            for dependency in _self_calls(legacy_methods[name]):
                if dependency in v2_methods:
                    continue
                if dependency in legacy_methods and dependency not in closure:
                    pending.append(dependency)

        self.assertNotIn("tick", closure)
        self.assertEqual(closure, EXPECTED_HISTORICAL_SUPPORT_CLOSURE)

    def test_charge_controller_v2_has_only_one_historical_import_edge(self) -> None:
        tree = ast.parse(V2_PATH.read_text(encoding="utf-8"))
        imports: list[tuple[str, tuple[str, ...]]] = []
        for node in tree.body:
            if isinstance(node, ast.ImportFrom) and node.module == "charge_logic":
                imports.append((node.module, tuple(alias.name for alias in node.names)))
        self.assertEqual(imports, [("charge_logic", ("ChargeController",))])


if __name__ == "__main__":
    unittest.main()
