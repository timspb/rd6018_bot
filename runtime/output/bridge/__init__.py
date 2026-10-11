"""Canonical physical bridge contracts and readback validation helpers."""

from .capabilities import HardwareCapability
from .snapshot import HardwareSnapshot, ReadbackValidation, validate_readback
from .adapter import PhysicalBridgeAdapter
from .audit import PhysicalExecutionAudit, PhysicalExecutionRecord
from .configuration import PhysicalExecutionConfig
from .executor import (
    GateValidation, PhysicalBridgeExecutor, PhysicalBridgeTransport,
    PhysicalExecutionError, PhysicalExecutionGate, PhysicalGateState,
)

__all__ = [
    "HardwareCapability", "HardwareSnapshot", "ReadbackValidation", "validate_readback",
    "PhysicalBridgeAdapter",
    "PhysicalExecutionAudit", "PhysicalExecutionRecord", "PhysicalExecutionConfig",
    "GateValidation", "PhysicalBridgeExecutor", "PhysicalBridgeTransport",
    "PhysicalExecutionError", "PhysicalExecutionGate", "PhysicalGateState",
]
