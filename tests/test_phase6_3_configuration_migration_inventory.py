"""Static checks for the Phase 6.3 configuration migration inventory.

These tests inspect tracked configuration/documentation only.  They do not
load production settings or invoke any runtime, transport, or actuator.
"""

from __future__ import annotations

from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "docs" / "RD6018_CONFIGURATION_MIGRATION_INVENTORY.md"


class _UniqueKeyLoader(yaml.SafeLoader):
    """SafeLoader variant that rejects duplicate mapping keys."""


def _construct_unique_mapping(loader: _UniqueKeyLoader, node, deep: bool = False):
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise AssertionError(f"duplicate YAML key: {key!r}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


class ConfigurationMigrationInventoryTests(unittest.TestCase):
    def test_configuration_ownership_map_is_complete(self) -> None:
        report = REPORT.read_text(encoding="utf-8")
        for category in ("KEEP", "MERGE", "CONFLICT", "REMOVE"):
            self.assertIn(f"`{category}`", report)

        required_parameters = (
            "Chemistry/profile names",
            "Manual MAIN voltage/current/minimum/hold",
            "Manual MIX voltage/current/delta/hold",
            "Device max temperature",
            "Watchdog timeout",
            "Physical readback timeout/poll",
            "OFF confirmation poll",
            "ESPHome lease TTL",
            "Lease renewal interval",
            "Transport selection",
            "HA/ESP credentials",
            "Charge session",
        )
        for parameter in required_parameters:
            self.assertIn(f"| {parameter} |", report, parameter)

        # Every inventory row must explicitly carry all migration columns.
        table_rows = [
            line for line in report.splitlines()
            if line.startswith("|") and line.count("|") >= 8
        ]
        self.assertGreaterEqual(len(table_rows), 20)
        for row in table_rows:
            if row.startswith("| Parameter") or row.startswith("|---"):
                continue
            cells = [cell.strip() for cell in row.strip("|").split("|")]
            self.assertGreaterEqual(len(cells), 7, row)
            self.assertIn(cells[-1], {"`KEEP`", "`MERGE`", "`CONFLICT`", "`REMOVE`"}, row)

    def test_tracked_yaml_has_no_hidden_duplicate_defaults(self) -> None:
        yaml_files = sorted((ROOT / "config").rglob("*.yaml"))
        self.assertTrue(yaml_files)
        for path in yaml_files:
            with self.subTest(path=path.relative_to(ROOT)):
                with path.open("r", encoding="utf-8") as handle:
                    yaml.load(handle, Loader=_UniqueKeyLoader)

    def test_report_does_not_promote_secret_values(self) -> None:
        report = REPORT.read_text(encoding="utf-8")
        self.assertIn("HA_TOKEN", report)
        self.assertIn("ESPHOME_API_KEY", report)
        self.assertIn("values intentionally not inventoried", report)
        self.assertNotIn("Bearer ", report)
        self.assertNotIn("password:", report.lower())


if __name__ == "__main__":
    unittest.main()
