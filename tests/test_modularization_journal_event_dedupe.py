import ast
import unittest
from pathlib import Path

from runtime.ui.components.journal_format import (
    _collapse_noisy_events,
    _remove_duplicate_events,
)


ROOT = Path(__file__).resolve().parents[1]


def event(ts, stage, name, suffix=""):
    field = name + suffix
    return f"[{ts}] | {stage} | 12.0 | 2.0 | 25 | 0.1 | {field}"


class JournalEventDeduplicationTests(unittest.TestCase):
    def test_empty_and_non_noisy_events_preserve_order(self):
        events = [event("2026-11-12 10:00:00", "MAIN", "START"),
                  event("2026-11-12 10:00:01", "CC", "STAGE_CHANGE")]
        self.assertEqual(_collapse_noisy_events([]), [])
        self.assertEqual(_remove_duplicate_events([]), [])
        self.assertEqual(_remove_duplicate_events(events), events)

    def test_adjacent_emergency_records_collapse_at_field_six(self):
        events = [event("2026-11-12 10:00:00", "MAIN", "EMERGENCY_UNAVAILABLE", " | detail=a"),
                  event("2026-11-12 10:00:01", "MAIN", "EMERGENCY_UNAVAILABLE", " | detail=b")]
        expected = event("2026-11-12 10:00:00", "MAIN", "EMERGENCY_UNAVAILABLE (x2)", " | detail=a")
        self.assertEqual(_collapse_noisy_events(events), [expected])
        # Existing first pass merges adjacent records independent of stage/time.
        self.assertEqual(_remove_duplicate_events(events), [expected])

    def test_separated_stage_transition_keeps_emergency_groups_separate(self):
        first = event("2026-11-12 10:00:00", "MAIN", "EMERGENCY_UNAVAILABLE")
        middle = event("2026-11-12 10:00:10", "MIX", "STAGE_CHANGE")
        last = event("2026-11-12 10:00:20", "MIX", "EMERGENCY_UNAVAILABLE")
        self.assertEqual(_remove_duplicate_events([first, middle, last]), [first, middle, last])

    def test_restore_same_stage_compression_and_stage_change(self):
        a = event("2026-11-12 10:00:00", "MAIN", "RESTORE")
        b = event("2026-11-12 10:00:01", "MAIN", "RESTORE", " | detail=last")
        c = event("2026-11-12 10:00:02", "MIX", "RESTORE")
        expected_b = event("2026-11-12 10:00:01", "MAIN", "RESTORE (x2)", " | detail=last")
        self.assertEqual(_remove_duplicate_events([a, b, c]), [expected_b, c])

    def test_emergency_600_second_window_and_greater_boundary(self):
        first = event("2026-11-12 10:00:00", "MAIN", "EMERGENCY_UNAVAILABLE")
        at_boundary = event("2026-11-12 10:10:00", "MAIN", "EMERGENCY_UNAVAILABLE")
        over_boundary = event("2026-11-12 10:10:01", "MAIN", "EMERGENCY_UNAVAILABLE")
        # Existing first pass merges adjacent emergency records before the
        # timestamp-aware pass, so both boundary cases have this same result.
        expected = event("2026-11-12 10:00:00", "MAIN", "EMERGENCY_UNAVAILABLE (x2)")
        self.assertEqual(_remove_duplicate_events([first, at_boundary]), [expected])
        self.assertEqual(_remove_duplicate_events([first, over_boundary]), [expected])

    def test_timestamp_parse_failures_do_not_raise_or_collapse(self):
        malformed_time = event("not-a-timestamp", "MAIN", "EMERGENCY_UNAVAILABLE")
        valid_time = event("2026-11-12 10:00:01", "MAIN", "EMERGENCY_UNAVAILABLE")
        separator = event("2026-11-12 10:00:00", "MAIN", "INFO")
        self.assertEqual(_remove_duplicate_events([malformed_time, separator, valid_time]),
                         [malformed_time, separator, valid_time])

    def test_malformed_six_field_events_and_mixed_state_events_are_preserved(self):
        malformed = "[2026-11-12 10:00:00] | MAIN | 12.0 | 2.0 | 25 | 0.1"
        states = [event("2026-11-12 10:00:01", "MAIN", "START"),
                  event("2026-11-12 10:00:02", "MAIN", "STOP"),
                  event("2026-11-12 10:00:03", "MAIN", "STAGE_CHANGE")]
        source = [malformed, *states]
        self.assertEqual(_remove_duplicate_events(source), source)

    def test_definitions_moved_and_reexported_without_wrappers(self):
        prod = ast.parse((ROOT / "runtime/production_runtime.py").read_text(encoding="utf-8"))
        journal = ast.parse((ROOT / "runtime/ui/components/journal_format.py").read_text(encoding="utf-8"))
        prod_defs = {n.name: n for n in prod.body if isinstance(n, ast.FunctionDef)}
        journal_defs = {n.name: n for n in journal.body if isinstance(n, ast.FunctionDef)}
        names = {"_collapse_noisy_events", "_remove_duplicate_events"}
        self.assertTrue(names.isdisjoint(prod_defs))
        for name in names:
            self.assertIn(name, journal_defs)
        imports = [n for n in prod.body if isinstance(n, ast.ImportFrom)
                   and n.module == "runtime.ui.components.journal_format"]
        imported = {alias.name: alias.asname for node in imports for alias in node.names}
        self.assertEqual({name: None for name in names}, {name: imported.get(name) for name in names})


if __name__ == "__main__":
    unittest.main()
