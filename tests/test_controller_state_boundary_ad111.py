from pathlib import Path
from types import SimpleNamespace

from runtime.charge.controller_state import (
    clear_link_lost_timestamp,
    mark_startup_observation_seen,
    set_observed_device_current,
)


def test_state_helpers_preserve_exact_nullable_current_and_flags():
    host = SimpleNamespace(
        _device_set_current=5.0,
        _link_lost_at=123.0,
        _d125_startup_observation_seen=False,
    )

    set_observed_device_current(host, None)
    clear_link_lost_timestamp(host)
    mark_startup_observation_seen(host)

    assert host._device_set_current is None
    assert host._link_lost_at == 0.0
    assert host._d125_startup_observation_seen is True


def test_cross_department_controller_observation_writes_use_state_owner():
    root = Path(__file__).resolve().parents[1]
    paths = (
        root / "application" / "controller_action_execution.py",
        root / "application" / "main_guard_runtime.py",
        root / "application" / "main_guard_transaction.py",
        root / "runtime" / "production_runtime.py",
        root / "runtime" / "startup_recovery.py",
    )
    forbidden = (
        "controller._last_known_output_on =",
        "controller._device_set_voltage =",
        "controller._device_set_current =",
        "controller._link_lost_at =",
        "charge_controller._last_known_output_on =",
        "charge_controller._device_set_voltage =",
        "charge_controller._device_set_current =",
        "charge_controller._link_lost_at =",
    )
    for path in paths:
        text = path.read_text(encoding="utf-8")
        for needle in forbidden:
            assert needle not in text, f"{path.name} bypasses controller_state: {needle}"
