"""Optional AI integration entry points, loaded only by explicit callers."""


def __getattr__(name: str):
    if name in {"ask_deepseek", "format_ai_snapshot", "format_recent_events"}:
        from . import engine

        return getattr(engine, name)
    if name == "handle_dialog_delivery":
        from .telegram_dialog import handle_dialog_delivery

        return handle_dialog_delivery
    raise AttributeError(name)


__all__ = [
    "ask_deepseek",
    "format_ai_snapshot",
    "format_recent_events",
    "handle_dialog_delivery",
]
