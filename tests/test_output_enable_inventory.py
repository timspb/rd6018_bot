"""Production Output-enable inventory.

Freezes every production call site that can change RD6018 Output state
(``turn_on`` / ``turn_off`` / ``safe_enable_output``), together with its owning
module and function. This is the mechanical "enable inventory" required before any
runtime ownership extraction: if a new direct actuator bypass appears, or an
existing one moves, this test fails and forces an explicit review.

READ-ONLY characterization: no production module is imported or modified; the
inventory is derived by parsing source with ``ast``.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

SKIP_DIRS = {
    ".git",
    ".venv",
    "tests",
    "esphome",
    "docs",
    "assets",
    "tools",
    "__pycache__",
    ".pytest_cache",
}

_ENABLE_METHODS = ("turn_on", "turn_off", "safe_enable_output")

# Frozen inventory: (module, function, "owner.method") for every production call.
ENABLE_CALLS = frozenset(
    {
        # Controller action execution is centralized in the application port so a
        # verified-enable stage commit can be withheld when Output ON fails.
        ("runtime_safety_strict.py", "turn_off", "super().turn_off"),
        ("runtime_safety_strict.py", "turn_on", "super().turn_on"),
        ("managed_runtime_safety.py", "turn_on", "super().turn_off"),
        ("managed_runtime_safety.py", "turn_on", "super().turn_on"),
        ("safe_output.py", "_force_off", "self.adapter.turn_off"),
        ("safe_output.py", "enable", "self.adapter.turn_on"),
        # Canonical application-scoped execution port. START, Mix-only
        # START and Manual converge here instead of keeping direct HA enable/OFF calls.
        ("application/execution_port.py", "enable", "self.execution_owner.safe_enable_output"),
        ("application/execution_port.py", "request_verified_on", "self.execution_owner.turn_on"),
        ("application/execution_port.py", "request_verified_off", "self.execution_owner.turn_off"),
    }
)


def _iter_production_files():
    for path in sorted(REPO_ROOT.rglob("*.py")):
        rel = path.relative_to(REPO_ROOT)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        yield rel.as_posix(), path


def scan_enable_calls():
    """Return the set of (module, function, "owner.method") output-enable call sites."""
    calls = set()
    for module, path in _iter_production_files():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for sub in ast.walk(node):
                if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute):
                    if sub.func.attr in _ENABLE_METHODS:
                        base = ast.unparse(sub.func.value)
                        calls.add((module, node.name, f"{base}.{sub.func.attr}"))
    return calls


class OutputEnableInventoryTests(unittest.TestCase):
    def test_enable_call_inventory_is_frozen(self):
        actual = scan_enable_calls()
        missing = sorted(ENABLE_CALLS - actual)
        added = sorted(actual - ENABLE_CALLS)
        self.assertEqual(
            added,
            [],
            "New production Output-enable call sites appeared (possible actuator "
            "bypass). Review and update ENABLE_CALLS deliberately: " + repr(added),
        )
        self.assertEqual(
            missing,
            [],
            "Production Output-enable call sites disappeared/moved. Review and "
            "update ENABLE_CALLS deliberately: " + repr(missing),
        )

    def test_production_runtime_has_no_direct_output_calls(self):
        direct_runtime_calls = {c for c in ENABLE_CALLS if c[0] == "runtime/production_runtime.py"}
        self.assertEqual(
            set(),
            direct_runtime_calls,
            "runtime/production_runtime.py must not regain direct Output authority after execution convergence",
        )


if __name__ == "__main__":
    unittest.main()
