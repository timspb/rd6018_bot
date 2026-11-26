from types import SimpleNamespace
from pathlib import Path

from runtime.charge.controller_state import (
    clear_link_lost_timestamp,
    mark_link_unavailable,
    mark_startup_observation_seen,
    set_last_known_output_on,
    set_observed_device_setpoints,
)


def test_controller_state_write_helpers_are_exact_and_side_effect_free():
    host = SimpleNamespace(
        _was_unavailable=False,
        _link_lost_at=0.0,
        _last_known_output_on=False,
        _device_set_voltage=None,
        _device_set_current=None,
    )

    mark_link_unavailable(host, lost_at_s=123.5)
    set_last_known_output_on(host, True)
    mark_startup_observation_seen(host)
    set_observed_device_setpoints(host, voltage_v=14.72, current_a=7.2)

    assert host._was_unavailable is True
    assert host._link_lost_at == 123.5
    clear_link_lost_timestamp(host)
    assert host._link_lost_at == 0.0
    assert host._last_known_output_on is True
    assert host._d125_startup_observation_seen is True
    assert host._device_set_voltage == 14.72
    assert host._device_set_current == 7.2


def test_production_runtime_does_not_mutate_controller_private_observation_fields():
    runtime = (
        Path(__file__).resolve().parents[1]
        / "runtime"
        / "production_runtime.py"
    ).read_text(encoding="utf-8")

    forbidden = (
        "charge_controller._was_unavailable =",
        "charge_controller._link_lost_at =",
        "charge_controller._last_known_output_on =",
        "charge_controller._device_set_voltage =",
        "charge_controller._device_set_current =",
        "charge_controller._d125_startup_observation_seen =",
    )
    for needle in forbidden:
        assert needle not in runtime


def test_startup_recovery_uses_controller_state_to_clear_consumed_link_gap():
    source = (
        Path(__file__).resolve().parents[1]
        / "runtime"
        / "startup_recovery.py"
    ).read_text(encoding="utf-8")

    assert "clear_link_lost_timestamp(controller)" in source
    assert "controller._link_lost_at =" not in source


def test_controller_action_execution_uses_controller_state_for_output_observation():
    source = (
        Path(__file__).resolve().parents[1]
        / "application"
        / "controller_action_execution.py"
    ).read_text(encoding="utf-8")

    assert "set_last_known_output_on(controller, True)" in source
    assert "controller._last_known_output_on =" not in source
