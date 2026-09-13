"""Shadow-only mapping toward the preserved V2 actuator representation."""

from .contract import LegacyActuatorCommand, ShadowExecutionRecord
from .mapping import map_safe_output_intent
from .shadow import ShadowOutputBridge

__all__ = ["LegacyActuatorCommand", "ShadowExecutionRecord", "map_safe_output_intent", "ShadowOutputBridge"]
