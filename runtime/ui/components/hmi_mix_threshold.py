"""Pure MIX threshold displays; read-only and never authorize charging."""
from __future__ import annotations


def cv_delta_status(minimum: float, actual: float, required: float) -> str:
    return (
        f"📉 Imin {minimum:.2f} A · ΔI "
        f"+{max(0.0, actual):.2f}/+{required:.2f} A"
        f" · цель I≥{minimum + required:.3f} A"
    )


def cc_delta_status(maximum: float, actual: float, required: float) -> str:
    return (
        f"📈 Vmax {maximum:.2f} V · ΔV "
        f"−{max(0.0, actual):.2f}/−{required:.2f} V"
        f" · цель U≤{maximum - required:.3f} V"
    )
