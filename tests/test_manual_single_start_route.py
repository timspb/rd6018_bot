"""Prevent Manual UI adapters from bypassing the application START route."""
from __future__ import annotations

import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ManualSingleStartRouteTests(unittest.TestCase):
    def test_ui_adapters_do_not_call_session_start_or_replace(self) -> None:
        for name in ('manual_context.py', 'manual_text.py'):
            with self.subTest(module=name):
                tree = ast.parse((ROOT / name).read_text(encoding='utf-8'))
                direct = [node for node in ast.walk(tree)
                          if isinstance(node, ast.Call)
                          and isinstance(node.func, ast.Attribute)
                          and node.func.attr in ('start', 'replace')
                          and isinstance(node.func.value, ast.Name)
                          and node.func.value.id == 'manager']
                self.assertEqual(direct, [], f'{name} bypasses Manual application route')

    def test_application_route_is_the_only_manual_start_adapter(self) -> None:
        source = (ROOT / 'manual_runtime.py').read_text(encoding='utf-8')
        self.assertIn('class ProductionManualUIRoute:', source)
        self.assertIn('async def submit_request(', source)
