"""Canonical, manual-only bench scenario definitions."""

from __future__ import annotations

from time import time

from .models import BenchScenario, BenchStep


def _scenario(scenario_id, operator, steps, capabilities=(), safety=()):
    return BenchScenario(scenario_id, operator, time(), tuple(capabilities), tuple(steps), tuple(safety))


def discovery_scenario(operator: str) -> BenchScenario:
    return _scenario("discovery", operator, [BenchStep("discover_capabilities"), BenchStep("read_snapshot", readback_required=True)])


def read_only_scenario(operator: str) -> BenchScenario:
    return _scenario("read_only", operator, [BenchStep("read_snapshot", readback_required=True)])


def verified_off_scenario(operator: str) -> BenchScenario:
    return _scenario("verified_off", operator, [
        BenchStep("disable_output", "disable"),
        BenchStep("verify_off", "read_output_state", True),
        BenchStep("verify_current", "read_current", True),
        BenchStep("reset_protection", "reset_protection"),
    ], safety=("safety_decision", "telemetry_fresh", "capability_match", "gate_armed"))


def parameter_write_scenario(operator: str) -> BenchScenario:
    return _scenario("safe_parameter_write", operator, [
        BenchStep("set_voltage", "set_voltage", True),
        BenchStep("set_current", "set_current", True),
    ], safety=("safety_decision", "telemetry_fresh", "capability_match", "gate_armed"))


def controlled_enable_scenario(operator: str) -> BenchScenario:
    return _scenario("controlled_enable", operator, [
        BenchStep("envelope_validation"),
        BenchStep("set_voltage", "set_voltage"),
        BenchStep("set_current", "set_current"),
        BenchStep("set_ovp", "set_ovp"),
        BenchStep("set_ocp", "set_ocp"),
        BenchStep("readback_compare", "readback", True),
        BenchStep("enable_output", "enable"),
        BenchStep("verify_on", "read_output_state", True),
    ], safety=("safety_decision", "telemetry_fresh", "capability_match", "gate_armed"))
