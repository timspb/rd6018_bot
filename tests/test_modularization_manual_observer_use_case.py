"""Structural and source-parity checks for the Manual observer extraction."""

import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HISTORICAL_MANUAL_MODE = (
    ROOT / "tests/fixtures/architecture/"
    "manual_mode_3c692554074b27805419a9b0767133a1c8d78150.py"
)


def _method(tree, class_name, method_name):
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == class_name)
    return next(
        node for node in cls.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == method_name
    )


class ManualObserverUseCaseTests(unittest.TestCase):
    def test_public_method_forwards_to_application_use_case(self):
        tree = ast.parse((ROOT / "manual_mode.py").read_text(encoding="utf-8"))
        method = _method(tree, "ManualSessionManager", "observe_once")
        self.assertEqual([arg.arg for arg in method.args.args], ["self"])
        self.assertEqual(len(method.body), 1)
        statement = method.body[0]
        self.assertIsInstance(statement, ast.Expr)
        call = statement.value
        self.assertIsInstance(call, ast.Await)
        self.assertIsInstance(call.value, ast.Call)
        self.assertIsInstance(call.value.func, ast.Name)
        self.assertEqual(call.value.func.id, "observe_manual_session_once")
        self.assertEqual([ast.unparse(arg) for arg in call.value.args], ["self"])

        usecase_tree = ast.parse((ROOT / "application/manual_observer_use_case.py").read_text(encoding="utf-8"))
        imports = {
            (node.module or "")
            for node in usecase_tree.body
            if isinstance(node, ast.ImportFrom)
        }
        imports.update(alias.name for node in usecase_tree.body if isinstance(node, ast.Import) for alias in node.names)
        self.assertNotIn("manual_mode", imports)
        self.assertNotIn("runtime.production_runtime", imports)

    def test_extracted_function_matches_head_observer_body(self):
        original = HISTORICAL_MANUAL_MODE.read_text(encoding="utf-8")
        old_method = _method(ast.parse(original), "ManualSessionManager", "observe_once")
        new_tree = ast.parse((ROOT / "application/manual_observer_use_case.py").read_text(encoding="utf-8"))
        new_function = next(
            node for node in new_tree.body
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "observe_manual_session_once"
        )
        new_body = list(new_function.body)
        alias = new_body.pop(0)
        self.assertIsInstance(alias, ast.Assign)
        self.assertEqual(ast.unparse(alias), "self = session")

        # The extracted module cannot import manual_mode's enum without creating
        # a cycle; resolve the same enum member through the session's enum type.
        old_body = ast.fix_missing_locations(ast.Module(body=old_method.body, type_ignores=[]))
        replacement = ast.parse("self.state is type(self.state).COOLING", mode="eval").body
        class CoolingNormalizer(ast.NodeTransformer):
            def visit_Compare(self, node):
                node = self.generic_visit(node)
                if ast.unparse(node) == "self.state is ManualSessionState.COOLING":
                    return replacement
                return node

        old_body = CoolingNormalizer().visit(old_body)
        class ExecutionReadNormalizer(ast.NodeTransformer):
            def visit_Call(self, node):
                node = self.generic_visit(node)
                if ast.unparse(node.func) == "self.app.hass.get_all_live":
                    return ast.parse("self.execution_port.read_live()", mode="eval").body
                return node

        old_body = ExecutionReadNormalizer().visit(old_body)

        class DeltaSampleNormalizer(ast.NodeTransformer):
            def visit_Assign(self, node):
                node = self.generic_visit(node)
                if ast.unparse(node) == "reason = self._delta_reason(live, now=now)":
                    sample_assignment = ast.parse(
                        "delta_sample = ManualDeltaSample("
                        "mode=resolve_regulation(live).value, "
                        "voltage_v=voltage, current_a=current)"
                    ).body[0]
                    node.value = ast.parse(
                        "self._delta_reason(delta_sample, now=now)", mode="eval"
                    ).body
                    return [sample_assignment, node]
                return node

        old_body = DeltaSampleNormalizer().visit(old_body)
        new_body_ast = ast.fix_missing_locations(ast.Module(body=new_body, type_ignores=[]))
        self.assertEqual(ast.dump(old_body, include_attributes=False), ast.dump(new_body_ast, include_attributes=False))


if __name__ == "__main__":
    unittest.main()
