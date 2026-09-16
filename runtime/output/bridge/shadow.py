"""Shadow bridge that records mapping and never executes it."""

from __future__ import annotations

from ..intent import SafeOutputIntent
from .contract import ShadowExecutionRecord
from .mapping import map_safe_output_intent


class ShadowOutputBridge:
    def map(self, intent: SafeOutputIntent) -> ShadowExecutionRecord:
        return ShadowExecutionRecord(intent, map_safe_output_intent(intent), False, "shadow_only")
