"""Registry mapping declarative UI actions to application intent kinds."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from application.intents import OperatorIntentKind

from ..actions import UIAction


@dataclass(frozen=True)
class UIActionRoute:
    action: UIAction
    intent_kind: OperatorIntentKind | None
    navigation_only: bool = False


DEFAULT_ACTION_ROUTES: Mapping[UIAction, UIActionRoute] = {
    UIAction.START_CHARGE: UIActionRoute(UIAction.START_CHARGE, OperatorIntentKind.START_CHARGE),
    UIAction.STOP_CHARGE: UIActionRoute(UIAction.STOP_CHARGE, OperatorIntentKind.STOP_CHARGE),
    UIAction.PAUSE_CHARGE: UIActionRoute(UIAction.PAUSE_CHARGE, OperatorIntentKind.PAUSE_CHARGE),
    UIAction.RESUME_CHARGE: UIActionRoute(UIAction.RESUME_CHARGE, OperatorIntentKind.RESUME_CHARGE),
    UIAction.SELECT_PROFILE: UIActionRoute(
        UIAction.SELECT_PROFILE, OperatorIntentKind.SELECT_CHARGE_PROFILE
    ),
    **{
        action: UIActionRoute(action, None, True)
        for action in (
            UIAction.OPEN_HOME,
            UIAction.OPEN_CHARGE,
            UIAction.OPEN_BATTERIES,
            UIAction.OPEN_MANUAL,
            UIAction.OPEN_DIAGNOSTICS,
            UIAction.OPEN_RECOVERY,
            UIAction.OPEN_MIX,
            UIAction.OPEN_SETTINGS,
            UIAction.OPEN_SERVICE,
            UIAction.OPEN_GRAPH,
            UIAction.OPEN_JOURNAL,
            UIAction.OPEN_ENTITIES,
            UIAction.OPEN_HELP,
        )
    },
}


def route_for(action: UIAction) -> UIActionRoute:
    try:
        return DEFAULT_ACTION_ROUTES[action]
    except KeyError as exc:
        raise ValueError(f"unregistered UI action: {action}") from exc


__all__ = ["DEFAULT_ACTION_ROUTES", "UIActionRoute", "route_for"]
