from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, Optional

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from operator_confirmation import ConfirmationStore


ADOPTED_STOP_CONFIRM_CALLBACK = "operator_adopted_stop"
ADOPTED_STOP_EXECUTE_CALLBACK = "operator_adopted_stop_execute"
ADOPTED_STOP_CANCEL_CALLBACK = "operator_done"


def _observer_stop_token(app: Any) -> Optional[str]:
    """Identity of the exact externally adopted Mix that may be stopped.

    The state name is intentionally not part of the token: ACTIVE may legitimately
    become OFF_PENDING while the same observer session is being contained. A new
    observer run changes ``started_at_s``; a process restart changes the object id and
    also discards the process-local confirmation store.
    """
    manager = getattr(app, "rd_control_mode_manager", None)
    if manager is None or not bool(getattr(manager, "hands_off", False)):
        return None

    observer = getattr(app, "rd_live_mix_observer", None)
    if observer is None:
        return None
    raw_state = getattr(observer, "state", None)
    state = str(getattr(raw_state, "value", raw_state) or "")
    if state not in {"active", "off_pending"}:
        return None

    try:
        started_at = float(getattr(observer, "started_at_s", 0.0) or 0.0)
    except (TypeError, ValueError):
        started_at = 0.0
    epoch = f"{started_at:.6f}" if started_at > 0.0 else f"object-{id(observer)}"
    return f"adopted-mix:{id(observer)}:{epoch}"


class DestructiveCallbackGuard(BaseMiddleware):
    """Bind the adopted-Mix OFF confirmation to one fresh observer session.

    The HMI has separate ``confirm`` and ``execute`` callbacks. Without server-side
    state, however, an old Telegram message containing the execute callback remains a
    valid verified-OFF command indefinitely. This middleware makes that second step a
    five-minute, chat/user-scoped, one-shot capability and rechecks the observer epoch
    immediately before the existing OFF handler is allowed to run.
    """

    def __init__(
        self,
        app: Any,
        *,
        confirmations: Optional[ConfirmationStore] = None,
    ) -> None:
        self.app = app
        self.confirmations = confirmations or ConfirmationStore()

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        callback = str(getattr(event, "data", "") or "")

        if callback == ADOPTED_STOP_CONFIRM_CALLBACK:
            expected = _observer_stop_token(self.app)
            result = await handler(event, data)
            # Bind only the exact observer that was present when the confirmation
            # workflow started. If it changed while the prompt was being rendered,
            # leave no executable grant behind.
            if expected is not None and _observer_stop_token(self.app) == expected:
                self.confirmations.issue_for_call(event, expected)
            return result

        if callback == ADOPTED_STOP_EXECUTE_CALLBACK:
            expected = self.confirmations.consume_for_call(event)
            if expected is None:
                answer = getattr(event, "answer", None)
                if callable(answer):
                    await answer(
                        "Подтверждение отсутствует, истекло или уже использовано",
                        show_alert=True,
                    )
                return None
            if _observer_stop_token(self.app) != expected:
                answer = getattr(event, "answer", None)
                if callable(answer):
                    await answer(
                        "Подхваченная Mix-сессия изменилась — Output не тронут",
                        show_alert=True,
                    )
                return None
            return await handler(event, data)

        if callback == ADOPTED_STOP_CANCEL_CALLBACK:
            self.confirmations.cancel_for_call(event)

        return await handler(event, data)


def install_operator_destructive_guard(app: Any) -> DestructiveCallbackGuard:
    existing = getattr(app, "_operator_destructive_guard", None)
    if isinstance(existing, DestructiveCallbackGuard):
        return existing

    middleware = DestructiveCallbackGuard(app)
    app.router.callback_query.outer_middleware.register(middleware)
    app._operator_destructive_guard = middleware
    return middleware
