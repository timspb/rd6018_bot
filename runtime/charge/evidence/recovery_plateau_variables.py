"""Recipe configuration owned by EFB recovery plateau evidence."""
from runtime.config.variable_spec import ChangeEffect, OverridePolicy, VariableSpec

def variable(key: str, default: float, unit: str, description: str,
             minimum: float, maximum: float) -> VariableSpec[float]:
    return VariableSpec(
        key="charge.recovery_plateau." + key,
        default=default, value_type=float, unit=unit,
        description=description, owner="runtime.charge.evidence.recovery_plateau",
        provenance="operator-approved EFB Recovery 90-120 minute model, 2026-11-05",
        override_policy=OverridePolicy.CONFIG_FILE,
        change_effect=ChangeEffect.RESTART_REQUIRED,
        minimum=minimum, maximum=maximum,
    )

ENABLED = VariableSpec(
    key="charge.recovery_plateau.enabled",
    default=0, value_type=int, unit="0/1",
    description="Opt-in adaptive plateau decisions in existing EFB Recovery MAIN owner.",
    owner="runtime.charge.evidence.recovery_plateau",
    provenance="operator-approved candidate, not deployed to node104",
    override_policy=OverridePolicy.CONFIG_FILE,
    change_effect=ChangeEffect.RESTART_REQUIRED,
    minimum=0, maximum=1,
)
MIN_WINDOW_MINUTES = variable("min_window_minutes", 90.0, "min", "Minimum continuous CV observation.", 60., 180.)
MAX_WINDOW_MINUTES = variable("max_window_minutes", 120.0, "min", "Maximum extended CV observation.", 90., 240.)
STRONG_DROP_A = variable("strong_plateau_drop_a", 0.01, "A", "Current drop qualifying for plateau.", 0., 0.5)
WEAK_DROP_A = variable("weak_plateau_drop_a", 0.02, "A", "Current drop that proves meaningful progress.", 0., 0.5)
END_SEGMENT_MINUTES = variable("end_segment_minutes", 15., "min", "Median interval at both window ends.", 5., 45.)
ALL = (ENABLED, MIN_WINDOW_MINUTES, MAX_WINDOW_MINUTES, STRONG_DROP_A, WEAK_DROP_A, END_SEGMENT_MINUTES)
