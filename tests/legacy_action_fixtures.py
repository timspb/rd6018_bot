"""Test-only mapping helper for historical action names."""

_MAPPING = {"START": "start_charge", "STOP": "stop_charge", "PROFILE_CHANGE": "select_profile"}


def map_action(action: str) -> str:
    try:
        return _MAPPING[action.strip().upper()]
    except KeyError as exc:
        raise ValueError(f"unsupported legacy action: {action}") from exc
