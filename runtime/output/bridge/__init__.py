"""Shadow-only mapping toward the preserved V2 actuator representation."""

from .contract import LegacyActuatorCommand, ShadowExecutionRecord
from .mapping import map_safe_output_intent
from .shadow import ShadowOutputBridge
from .capabilities import HardwareCapability
from .snapshot import HardwareSnapshot, ReadbackValidation, validate_readback
from .adapter import PhysicalBridgeAdapter
from .audit import PhysicalExecutionAudit, PhysicalExecutionRecord
from .configuration import PhysicalExecutionConfig
from .executor import GateValidation, PhysicalBridgeTransport, PhysicalExecutionError, PhysicalExecutionGate, PhysicalGateState

__all__ = [
    "LegacyActuatorCommand", "ShadowExecutionRecord", "map_safe_output_intent", "ShadowOutputBridge",
    "HardwareCapability", "HardwareSnapshot", "ReadbackValidation", "validate_readback",
    "PhysicalBridgeAdapter",
    "PhysicalExecutionAudit", "PhysicalExecutionRecord", "PhysicalExecutionConfig",
    "GateValidation", "PhysicalBridgeTransport",
    "PhysicalExecutionError", "PhysicalExecutionGate", "PhysicalGateState",
]
