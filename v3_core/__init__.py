"""Pure V3 core; exports are lazy to keep canonical-event imports isolated."""

__all__ = ["V3Composition", "ActuatorIntent", "ActuatorOperation", "TelemetrySnapshot"]


def __getattr__(name: str):
    if name == "V3Composition":
        from .composition import V3Composition
        return V3Composition
    if name in {"ActuatorIntent", "ActuatorOperation", "TelemetrySnapshot"}:
        from .contracts import ActuatorIntent, ActuatorOperation, TelemetrySnapshot
        return {"ActuatorIntent": ActuatorIntent, "ActuatorOperation": ActuatorOperation, "TelemetrySnapshot": TelemetrySnapshot}[name]
    raise AttributeError(name)
