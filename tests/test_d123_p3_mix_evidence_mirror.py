import ast
import inspect
import unittest
from pathlib import Path

from runtime.charge.evidence import mix_observation as owner


ROOT = Path(__file__).resolve().parents[1]


class MixEvidenceMirrorTests(unittest.TestCase):
    def test_cv_and_cc_mirrors_are_independent(self):
        class Host:
            i_min_recorded = 9.0
            v_max_recorded = 19.0

        host = Host()
        cv = owner.build_mix_evidence_mirror(
            is_cv=True, is_cc=False, current_min_a=0.4, voltage_max_v=16.5
        )
        owner.apply_mix_evidence_mirror(host, cv)
        self.assertEqual(host.i_min_recorded, 0.4)
        self.assertEqual(host.v_max_recorded, 19.0)

        cc = owner.build_mix_evidence_mirror(
            is_cv=False, is_cc=True, current_min_a=0.3, voltage_max_v=16.47
        )
        owner.apply_mix_evidence_mirror(host, cc)
        self.assertEqual(host.i_min_recorded, 0.4)
        self.assertEqual(host.v_max_recorded, 16.47)

    def test_missing_metrics_do_not_overwrite_existing_mirrors(self):
        class Host:
            i_min_recorded = 0.7
            v_max_recorded = 16.2

        host = Host()
        mirror = owner.build_mix_evidence_mirror(
            is_cv=True, is_cc=True, current_min_a=None, voltage_max_v=None
        )
        owner.apply_mix_evidence_mirror(host, mirror)
        self.assertEqual(host.i_min_recorded, 0.7)
        self.assertEqual(host.v_max_recorded, 16.2)

    def test_controller_delegates_once_without_inline_mirror_assignments(self):
        source = (ROOT / "runtime/charge/runtime/mix_scaffold.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        calls = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "apply_mix_evidence_mirror"
        ]
        self.assertEqual(len(calls), 1)
        controller_source = (ROOT / "charge_controller.py").read_text(encoding="utf-8")
        self.assertIn("return apply_mix_authority_tick(", controller_source)
        self.assertNotIn("self.i_min_recorded = metrics.current_min_a", controller_source)
        self.assertNotIn("self.v_max_recorded = metrics.voltage_max_v", controller_source)

        from runtime.charge.runtime import mix_scaffold
        owner_source = inspect.getsource(mix_scaffold.apply_mix_authority_tick)
        for forbidden in ("execution_port", "set_voltage", "set_current", "turn_on", "turn_off"):
            self.assertNotIn(forbidden, owner_source)


if __name__ == "__main__":
    unittest.main()
