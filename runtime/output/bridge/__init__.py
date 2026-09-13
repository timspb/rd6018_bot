"""Shadow-only mapping toward the preserved V2 actuator representation."""

from .contract import LegacyActuatorCommand, ShadowExecutionRecord
from .mapping import map_safe_output_intent
from .shadow import ShadowOutputBridge
from .capabilities import HardwareCapability
from .snapshot import HardwareSnapshot, ReadbackValidation, validate_readback
from .adapter import LegacyHardwareAdapter, PhysicalBridgeAdapter

__all__ = [
    "LegacyActuatorCommand", "ShadowExecutionRecord", "map_safe_output_intent", "ShadowOutputBridge",
    "HardwareCapability", "HardwareSnapshot", "ReadbackValidation", "validate_readback",
    "LegacyHardwareAdapter", "PhysicalBridgeAdapter",
]
