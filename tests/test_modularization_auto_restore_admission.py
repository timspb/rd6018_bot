"""Pure contract tests for AUTO restore admission extraction."""

from __future__ import annotations

import ast
import textwrap
import unittest
from types import SimpleNamespace
from pathlib import Path

from runtime.charge import restore_admission
from runtime.charge.terminal_intent import DONE_COMPLETION_STORAGE, DONE_OUTPUT_ON


class AutoRestoreAdmissionTests(unittest.TestCase):
    def test_active_non_done_session_allows_restore(self):
        host = SimpleNamespace(current_stage="MAIN", STAGE_DONE="DONE")
        self.assertTrue(restore_admission.restore_allows_auto_enable(host))

    def test_done_allows_only_authoritative_explicit_storage_on(self):
        base = {
            "current_stage": "DONE",
            "STAGE_DONE": "DONE",
            "_done_outcome_authoritative": True,
            "_done_completion_kind": DONE_COMPLETION_STORAGE,
            "_done_output_intent": DONE_OUTPUT_ON,
        }
        self.assertTrue(restore_admission.restore_allows_auto_enable(SimpleNamespace(**base)))
        for changes in (
            {"_done_outcome_authoritative": False},
            {"_done_completion_kind": "terminal"},
            {"_done_output_intent": "off"},
            {"_done_output_intent": "ON"},
            {"_done_output_intent": None},
        ):
            with self.subTest(changes=changes):
                self.assertFalse(restore_admission.restore_allows_auto_enable(
                    SimpleNamespace(**(base | changes))
                ))

    def test_cooling_is_denied_and_missing_optional_cooling_stage_is_supported(self):
        cooling = SimpleNamespace(
            current_stage="COOLING", STAGE_DONE="DONE", STAGE_COOLING="COOLING"
        )
        without_optional_stage = SimpleNamespace(current_stage="MAIN", STAGE_DONE="DONE")
        self.assertFalse(restore_admission.restore_allows_auto_enable(cooling))
        self.assertTrue(restore_admission.restore_allows_auto_enable(without_optional_stage))

    def test_explicit_storage_document_requires_exact_version_and_tokens(self):
        valid = {
            "done_state_version": 1,
            "completion_kind": "storage",
            "output_intent": "on",
        }
        self.assertTrue(restore_admission._explicit_storage_outcome(valid))
        for document in (
            valid | {"done_state_version": "1"},
            valid | {"done_state_version": 2},
            valid | {"completion_kind": "Storage"},
            valid | {"output_intent": "ON"},
            {"completion_kind": "storage", "output_intent": "on"},
        ):
            with self.subTest(document=document):
                self.assertFalse(restore_admission._explicit_storage_outcome(document))

    def test_persistence_reexports_same_pure_authorities(self):
        from runtime.charge import persistence

        self.assertIs(persistence.restore_allows_auto_enable,
                      restore_admission.restore_allows_auto_enable)
        self.assertIs(persistence._explicit_storage_outcome,
                      restore_admission._explicit_storage_outcome)
        self.assertIs(persistence.DONE_STATE_VERSION, restore_admission.DONE_STATE_VERSION)

    def test_normalized_ast_matches_approved_original_algorithms(self):
        source = Path(restore_admission.__file__).read_text(encoding="utf-8")
        module = ast.parse(source)
        class StripAnnotations(ast.NodeTransformer):
            def visit_FunctionDef(self, node):
                node.returns = None
                for argument in (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs):
                    argument.annotation = None
                if node.args.vararg is not None:
                    node.args.vararg.annotation = None
                if node.args.kwarg is not None:
                    node.args.kwarg.annotation = None
                return self.generic_visit(node)

        StripAnnotations().visit(module)
        actual = {
            node.name: ast.dump(node, annotate_fields=True, include_attributes=False)
            for node in module.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name in {"_explicit_storage_outcome", "restore_allows_auto_enable"}
        }
        expected_source = textwrap.dedent(
            '''
            def _explicit_storage_outcome(document):
                return (
                    document.get("done_state_version") == DONE_STATE_VERSION
                    and document.get("completion_kind") == DONE_COMPLETION_STORAGE
                    and document.get("output_intent") == DONE_OUTPUT_ON
                )

            def restore_allows_auto_enable(host):
                """Allow auto-enable only for active sessions or explicit managed Storage."""
                if host.current_stage == host.STAGE_DONE:
                    return bool(
                        getattr(host, "_done_outcome_authoritative", False)
                        and getattr(host, "_done_completion_kind", None)
                        == DONE_COMPLETION_STORAGE
                        and getattr(host, "_done_output_intent", DONE_OUTPUT_OFF)
                        == DONE_OUTPUT_ON
                    )
                cooling_stage = getattr(host, "STAGE_COOLING", None)
                if cooling_stage is not None and host.current_stage == cooling_stage:
                    return False
                return True
            '''
        )
        expected_module = ast.parse(expected_source)
        StripAnnotations().visit(expected_module)
        expected = {
            node.name: ast.dump(node, annotate_fields=True, include_attributes=False)
            for node in expected_module.body
            if isinstance(node, ast.FunctionDef)
        }
        self.assertEqual(actual, expected)

    def test_module_import_boundary_is_pure_and_narrow(self):
        tree = ast.parse(Path(restore_admission.__file__).read_text(encoding="utf-8"))
        imports = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        imports.update(
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        )
        self.assertEqual(imports, {"__future__", "typing", "runtime.charge.terminal_intent"})
        terminal_import = next(
            node for node in tree.body
            if isinstance(node, ast.ImportFrom)
            and node.module == "runtime.charge.terminal_intent"
        )
        self.assertEqual(
            {alias.name for alias in terminal_import.names},
            {"DONE_COMPLETION_STORAGE", "DONE_OUTPUT_OFF", "DONE_OUTPUT_ON"},
        )


if __name__ == "__main__":
    unittest.main()
