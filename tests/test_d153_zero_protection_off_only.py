"""D153: retired OVP/OCP software controls must not reappear.

Hardware registers remain untouched. Independent V/I and verified-OFF
protections are tested by the managed-output and runtime-safety suites.
"""
from __future__ import annotations

import ast
import unittest
from pathlib import Path

from application.execution_port import ExecutionPort
from hass_api import HassClient
from runtime.safety.runtime_guard import RuntimeSafetyGuard


class RetiredProtectionInterfaceTests(unittest.TestCase):
    def test_no_public_or_private_ovp_ocp_setters(self):
        for cls in (RuntimeSafetyGuard, HassClient, ExecutionPort):
            with self.subTest(owner=cls.__name__):
                exposed = set(dir(cls))
                self.assertTrue({"set_ovp", "set_ocp", "_set_ovp", "_set_ocp"}.isdisjoint(exposed))

    def test_no_legacy_register_writes_in_control_boundaries(self):
        for rel in (
            "runtime/safety/runtime_guard.py",
            "hass_api.py",
            "application/execution_port.py",
        ):
            with self.subTest(path=rel):
                tree = ast.parse(Path(rel).read_text(encoding="utf-8"))
                names = {
                    node.attr for node in ast.walk(tree)
                    if isinstance(node, ast.Attribute)
                }
                self.assertTrue(
                    {"set_ovp", "set_ocp", "_set_ovp", "_set_ocp"}.isdisjoint(names)
                )


if __name__ == "__main__":
    unittest.main()
