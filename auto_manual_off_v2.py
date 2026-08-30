from __future__ import annotations

from typing import Any, Dict


def _force_manual_off_inert_for_auto(args: tuple[Any, ...], kwargs: Dict[str, Any]) -> tuple[tuple[Any, ...], Dict[str, Any]]:
    """Keep legacy Manual-OFF armed state out of AUTO chemistry authority.

    The legacy bot evaluates the persistent OFF condition independently and performs
    a terminal hard-stop when it fires. Production V2 must therefore never let the
    mere *presence* of that condition alter Main/Recovery/Mix/timeout decisions.
    """
    forwarded = list(args)
    forwarded_kwargs = dict(kwargs)

    # ChargeController.tick(..., output_is_on=None, manual_off_active=False, is_cc=None)
    if len(forwarded) >= 7:
        forwarded[6] = False
        forwarded_kwargs.pop("manual_off_active", None)
    else:
        forwarded_kwargs["manual_off_active"] = False
    return tuple(forwarded), forwarded_kwargs


def install_auto_manual_off_contract(app: Any) -> None:
    """Make Manual-OFF an asynchronous terminal kill condition only.

    `bot_legacy.data_logger()` still owns condition evaluation. When a condition is
    reached it calls `_hard_stop_charge()`, which turns Output OFF and stops/clears the
    AUTO session. Until that moment AUTO chemistry proceeds exactly as if no Manual-OFF
    condition were armed.
    """
    controller = app.charge_controller
    if getattr(controller, "_v2_auto_manual_off_contract_installed", False):
        return

    original_tick = controller.tick

    async def tick_without_manual_off_authority(*args: Any, **kwargs: Any):
        safe_args, safe_kwargs = _force_manual_off_inert_for_auto(args, kwargs)
        return await original_tick(*safe_args, **safe_kwargs)

    controller.tick = tick_without_manual_off_authority
    controller._v2_auto_manual_off_contract_installed = True
