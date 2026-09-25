import ast
import pathlib
import unittest


class CallbackOwnershipTests(unittest.TestCase):
    """Exact callback literals must have one source owner in the repository."""

    def test_no_duplicate_exact_callback_registration(self):
        registrations = {}
        for path in pathlib.Path(".").glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                for decorator in node.decorator_list:
                    if not (
                        isinstance(decorator, ast.Call)
                        and isinstance(decorator.func, ast.Attribute)
                        and decorator.func.attr == "callback_query"
                    ):
                        continue
                    expression = decorator.args[0] if decorator.args else None
                    if not (
                        isinstance(expression, ast.Compare)
                        and len(expression.ops) == 1
                        and isinstance(expression.ops[0], ast.Eq)
                        and isinstance(expression.comparators[0], ast.Constant)
                        and isinstance(expression.comparators[0].value, str)
                    ):
                        continue
                    callback = expression.comparators[0].value
                    registrations.setdefault(callback, []).append(
                        f"{path}:{node.lineno}:{node.name}"
                    )

        duplicates = {key: value for key, value in registrations.items() if len(value) > 1}
        self.assertEqual({}, duplicates)


if __name__ == "__main__":
    unittest.main()
