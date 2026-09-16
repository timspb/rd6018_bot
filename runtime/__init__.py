"""Isolated V3 runtime boundaries.

This package is intentionally dependency-free during Phase 3A.  It does not
compose the current bot runtime and has no actuator capability.
"""

from .app import RuntimeApp
from .dependencies import RuntimeDependencies
from .lifecycle import LifecycleManager, LifecycleState

__all__ = ["LifecycleManager", "LifecycleState", "RuntimeApp", "RuntimeDependencies"]
