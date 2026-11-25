"""Optional AI integration entry points, loaded only by explicit callers."""


def __getattr__(name: str):
    if name == "handle_dialog_delivery":
        from .telegram_dialog import handle_dialog_delivery

        return handle_dialog_delivery
    raise AttributeError(name)


__all__ = ["handle_dialog_delivery"]
