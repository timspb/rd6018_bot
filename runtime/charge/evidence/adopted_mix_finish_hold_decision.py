"""Pure elapsed-time decision for the adopted-MIX finish hold."""

import math

from runtime.safety.runtime_guard import RuntimeSafetyError


def adopted_mix_finish_hold_complete(
    anchor_mono_s: float,
    now_mono_s: float,
    hold_s: float,
) -> bool:
    """Return whether a monotonic hold reached its configured duration.

    The caller owns the anchor and clock. Invalid or backwards elapsed time keeps
    the adopted-MIX coordinator's established safety error contract.
    """
    held = float(now_mono_s) - float(anchor_mono_s)
    if not math.isfinite(held) or held < 0:
        raise RuntimeSafetyError("MIX_ADOPTED finish-hold monotonic clock moved backwards")
    return held >= float(hold_s)


__all__ = ["adopted_mix_finish_hold_complete"]
