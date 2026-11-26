"""P5-9E stateful parity tests for D062 active clock and Delta epoch."""

from __future__ import annotations

import ast
import math
import unittest
from pathlib import Path
from unittest.mock import Mock

from dataclasses import dataclass
from enum import Enum


class RuntimeSafetyError(Exception):
    """Local stand-in for the exception symbol injected into the actual methods."""


class ManagedMixState(str, Enum):
    ACTIVE = "active"
    IDLE = "idle"


@dataclass(frozen=True)
class ManagedAdoptionFingerprint:
    set_voltage_v: float
    set_current_a: float


def isolated_coordinator_class():
    """Compile the actual stateful methods while omitting module/UI imports."""
    source = Path("rd_managed_mix.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    owner = next(node for node in tree.body if isinstance(node, ast.ClassDef)
                 and node.name == "ManagedMixAdoptionCoordinator")
    methods = [node for node in owner.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
               and node.name in {"active", "_reset_delta_epoch", "_advance_active_clock"}]
    isolated = ast.ClassDef(name="Coordinator", bases=[], keywords=[], body=methods, decorator_list=[])
    module = ast.fix_missing_locations(ast.Module(body=[isolated], type_ignores=[]))
    namespace = {"ManagedMixState": ManagedMixState, "ManagedAdoptionFingerprint": ManagedAdoptionFingerprint,
                 "RuntimeSafetyError": RuntimeSafetyError, "math": math, "property": property}
    exec(compile(module, "rd_managed_mix.py isolated methods", "exec"), namespace)
    return namespace["Coordinator"]


Coordinator = isolated_coordinator_class()


class Clock:
    def __init__(self, mono=100.0, wall=1_000.0):
        self.mono = float(mono)
        self.wall = float(wall)

    def monotonic(self):
        return self.mono

    def time(self):
        return self.wall


class CoordinatorFixture:
    @staticmethod
    def make(clock):
        coordinator = Coordinator.__new__(Coordinator)
        coordinator.state = ManagedMixState.ACTIVE
        coordinator.adopted_active_elapsed_s = 12.0
        coordinator._active_anchor_mono = None
        coordinator._finish_hold_anchor_mono = 17.0
        coordinator.finish_hold_started_at_s = 900.0
        coordinator.last_source_timestamp_s = 800.0
        coordinator.current_authority = None
        coordinator.last_status = "before"
        coordinator._monotonic = clock.monotonic
        coordinator._wall_time = clock.time
        coordinator.analyzer = Mock()
        coordinator._persist = Mock()
        return coordinator


class AdoptedMixEvidenceClockTests(unittest.TestCase):
    def test_inactive_clears_anchor_without_changing_elapsed(self):
        clock = Clock()
        c = CoordinatorFixture.make(clock)
        c.state = ManagedMixState.IDLE
        c.adopted_active_elapsed_s = 31.5
        c._active_anchor_mono = 90.0
        c._advance_active_clock()
        self.assertIsNone(c._active_anchor_mono)
        self.assertEqual(c.adopted_active_elapsed_s, 31.5)

    def test_first_active_sample_anchors_and_next_sample_accumulates_delta(self):
        clock = Clock(mono=100.0)
        c = CoordinatorFixture.make(clock)
        c._advance_active_clock()
        self.assertEqual(c._active_anchor_mono, 100.0)
        self.assertEqual(c.adopted_active_elapsed_s, 12.0)
        clock.mono = 107.25
        c._advance_active_clock()
        self.assertEqual(c.adopted_active_elapsed_s, 19.25)
        self.assertEqual(c._active_anchor_mono, 107.25)

    def test_inactive_to_active_reanchors_without_counting_inactive_gap(self):
        clock = Clock(mono=100.0)
        c = CoordinatorFixture.make(clock)
        c._active_anchor_mono = 90.0
        c.state = ManagedMixState.IDLE
        c._advance_active_clock()
        clock.mono = 500.0
        c.state = ManagedMixState.ACTIVE
        c._advance_active_clock()
        self.assertEqual(c._active_anchor_mono, 500.0)
        self.assertEqual(c.adopted_active_elapsed_s, 12.0)

    def test_backward_and_nonfinite_deltas_throw_without_advancing_evidence(self):
        for now in (99.0, float("nan"), float("inf")):
            with self.subTest(now=now):
                clock = Clock(mono=now)
                c = CoordinatorFixture.make(clock)
                c._active_anchor_mono = 100.0
                before = (c.adopted_active_elapsed_s, c._active_anchor_mono)
                with self.assertRaises(RuntimeSafetyError):
                    c._advance_active_clock()
                self.assertEqual((c.adopted_active_elapsed_s, c._active_anchor_mono), before)

    def test_delta_epoch_uses_explicit_source_barrier_and_resets_hold_once(self):
        clock = Clock(wall=1_234.0)
        c = CoordinatorFixture.make(clock)
        fingerprint = ManagedAdoptionFingerprint(15.2, 0.7)
        c._reset_delta_epoch(fingerprint, "explicit", source_barrier_s=321.5)
        self.assertEqual(c.current_authority, fingerprint)
        self.assertIsNone(c.finish_hold_started_at_s)
        self.assertIsNone(c._finish_hold_anchor_mono)
        self.assertEqual(c.last_source_timestamp_s, 321.5)
        c.analyzer.reset_stage.assert_called_once_with("MIX_ADOPTED", target_voltage_v=15.2)
        c._persist.assert_called_once_with()

    def test_delta_epoch_without_source_barrier_uses_wall_time(self):
        clock = Clock(wall=2_345.0)
        c = CoordinatorFixture.make(clock)
        c._reset_delta_epoch(ManagedAdoptionFingerprint(15.2, 0.7), "wall")
        self.assertEqual(c.last_source_timestamp_s, 2_345.0)
        c._persist.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
