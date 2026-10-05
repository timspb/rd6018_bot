"""Composition helper for operator intent routing.

This module owns command-handler wiring only.  Read-model providers receive the
finished dispatcher and never require the production runtime object.
"""

from __future__ import annotations

from typing import Any

from .intents import IntentDispatcher, OperatorIntentKind
from .off_condition_command import OffConditionCommandHandler
from .pause_command import PauseCommandHandler
from .profile_command import ProfileCommandHandler
from .stop_command import StopCommandHandler


def build_operator_intent_dispatcher(app: Any) -> IntentDispatcher:
    pause_handler = PauseCommandHandler().route
    return IntentDispatcher(
        stop_handler=StopCommandHandler().route,
        routes={
            OperatorIntentKind.PAUSE_CHARGE: pause_handler,
            OperatorIntentKind.RESUME_CHARGE: pause_handler,
            OperatorIntentKind.SELECT_CHARGE_PROFILE: ProfileCommandHandler().route,
            OperatorIntentKind.SET_OFF_CONDITION: OffConditionCommandHandler(app).route,
        },
    )


__all__ = ["build_operator_intent_dispatcher"]
