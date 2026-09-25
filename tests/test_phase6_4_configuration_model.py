"""Phase 6.4 validated configuration model tests; no runtime wiring."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from application.configuration_authority import ConfigurationParameter, ConfigurationSection
from application.configuration_model import (
    ConfigurationConflictError,
    ConfigurationMissingError,
    ConfigurationModel,
    EnvironmentSourceAdapter,
    PythonConstantsAdapter,
    YamlSourceAdapter,
    default_configuration_authority,
)


ROOT = Path(__file__).resolve().parents[1]


class ConfigurationModelTests(unittest.TestCase):
    def test_all_nine_sections_have_typed_defaults(self) -> None:
        authority = default_configuration_authority()
        model = ConfigurationModel.resolve(authority, [])
        for section in ("charge", "strategy", "safety", "containment", "lease", "execution", "transport", "ui", "persistence"):
            self.assertTrue(hasattr(model, section))
        self.assertEqual(18.0, model.get("safety.max_voltage_v"))
        self.assertEqual("default", model.value("lease.ttl_s").source)

    def test_yaml_python_and_env_sources_are_read_only_and_resolved(self) -> None:
        authority = default_configuration_authority()
        with tempfile.TemporaryDirectory() as directory:
            yaml_path = Path(directory) / "source.yaml"
            yaml_path.write_text("limits:\n  voltage: 18\n", encoding="utf-8")
            yaml_values = YamlSourceAdapter({"limits.voltage": "safety.max_voltage_v"}).read(yaml_path)

            python_path = Path(directory) / "source.py"
            python_path.write_text("TIMEOUT = 15\n", encoding="utf-8")
            python_values = PythonConstantsAdapter({"TIMEOUT": "execution.readback_timeout_s"}).read(python_path)

            env_values = EnvironmentSourceAdapter({"RD_TIMEOUT": "15"}).read({"transport.ha_timeout_s": "RD_TIMEOUT"})
            model = ConfigurationModel.resolve(authority, (yaml_values, python_values, env_values))

        self.assertEqual(18.0, model.get("safety.max_voltage_v"))
        self.assertEqual(15.0, model.get("execution.readback_timeout_s"))
        self.assertEqual(15.0, model.get("transport.ha_timeout_s"))

    def test_conflicting_values_are_detected(self) -> None:
        authority = default_configuration_authority()
        with self.assertRaises(ConfigurationConflictError):
            ConfigurationModel.resolve(authority, ({"safety.max_voltage_v": 18}, {"safety.max_voltage_v": 17}))

    def test_required_values_are_detected(self) -> None:
        parameter = ConfigurationParameter(
            "safety.required", ConfigurationSection.SAFETY, "Safety", float, 1.0,
            lambda value: value > 0, "required test value", "test source", True,
        )
        from application.configuration_authority import ConfigurationAuthority
        with self.assertRaises(ConfigurationMissingError):
            ConfigurationModel.resolve(ConfigurationAuthority({parameter.key: parameter}), [])

    def test_no_production_wiring(self) -> None:
        text = (ROOT / "application" / "configuration_model.py").read_text(encoding="utf-8")
        self.assertNotIn("import bot", text)
        self.assertNotIn("controller.start", text)
        self.assertNotIn("controller.stop", text)
        self.assertNotIn("SafeOutputCoordinator", text)


if __name__ == "__main__":
    unittest.main()
