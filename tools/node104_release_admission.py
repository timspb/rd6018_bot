"""D124 release admission classification; never grants actuator/host authority.

Historical physical evidence is retained. A Python-only release does not require
recertification of every firmware hardware test, while changed control authority
requires targeted regression and a fresh native OFF gate before D090 deployment.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import PurePosixPath

CONTROL_PREFIXES = (
    "runtime/charge/", "runtime/physical/", "runtime_safety", "edge_safety_lease",
    "application/execution_port.py", "application/controller_action_execution.py",
    "application/charge_stage_tick.py", "application/charge_session_tick.py",
    "application/production_", "production_bootstrap.py", "charge_controller.py",
    "hass_api.py", "tools/node104_d090_",
)
FIRMWARE_PREFIXES = ("esphome/", "firmware/", "esp32/")

@dataclass(frozen=True)
class Admission:
    classification: str
    changed_control_paths: tuple[str, ...]
    changed_firmware_paths: tuple[str, ...]
    requires_targeted_control_validation: bool
    requires_fresh_native_off: bool = True
    requires_d090_rollback: bool = True
    requires_repeat_all_physical_cases: bool = False
    requires_operator_signature: bool = False


def classify(changed_paths: list[str], *, firmware_version_changed: bool = False) -> Admission:
    if not changed_paths or any(not isinstance(p, str) or not p or
                                PurePosixPath(p).is_absolute() or ".." in PurePosixPath(p).parts
                                for p in changed_paths):
        raise ValueError("missing or invalid change inventory")
    control = tuple(sorted({p for p in changed_paths if p.startswith(CONTROL_PREFIXES)}))
    firmware = tuple(sorted({p for p in changed_paths if p.startswith(FIRMWARE_PREFIXES)}))
    category = "firmware_physical_change" if firmware or firmware_version_changed else (
        "python_control_change" if control else "python_noncontrol_change"
    )
    return Admission(category, control, firmware, bool(control or firmware or firmware_version_changed),
                     requires_repeat_all_physical_cases=bool(firmware or firmware_version_changed))
