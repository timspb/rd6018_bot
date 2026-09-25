from __future__ import annotations

from time import time

from runtime.output.bridge import HardwareSnapshot

from .comparator import PhysicalStateComparator
from .evidence import PhysicalVerificationEvidence
from .models import PostActionVerificationResult, PreActionVerificationResult, VerificationResult


class PhysicalVerificationService:
    """Verification-only service; it never sends a command to a transport."""

    def __init__(self, comparator: PhysicalStateComparator):
        self.comparator = comparator

    def verify_pre_action(self, requested_state: HardwareSnapshot, observed_state: HardwareSnapshot,
                          *, transport: str, require_fields: tuple[str, ...] = ()) -> PreActionVerificationResult:
        result, differences = self.comparator.compare(requested_state, observed_state, require_fields=require_fields)
        return PreActionVerificationResult(requested_state, observed_state, differences, time(), transport, result)

    def verify_post_action(self, action: str, expected_state: HardwareSnapshot, observed_state: HardwareSnapshot,
                           *, require_fields: tuple[str, ...] = ()) -> PostActionVerificationResult:
        result, differences = self.comparator.compare(expected_state, observed_state, require_fields=require_fields)
        return PostActionVerificationResult(action, expected_state, observed_state, differences, time(), result)

    def build_evidence(self, *, before_snapshot, requested_state, write_result, pre_readback,
                       pre_comparison, action, post_readback, post_comparison) -> PhysicalVerificationEvidence:
        final = VerificationResult.MATCH if (
            getattr(pre_comparison, "result", None) == VerificationResult.MATCH
            and getattr(post_comparison, "result", None) == VerificationResult.MATCH
        ) else VerificationResult.FAILED
        return PhysicalVerificationEvidence(before_snapshot, requested_state, write_result, pre_readback,
                                             pre_comparison, action, post_readback, post_comparison, final)
