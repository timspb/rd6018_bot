"""AI integration entrypoint for the explicit optional-module manager."""
from __future__ import annotations

from typing import Any


def install(app: Any) -> None:
    from integrations.ai.telegram_screen import install_analysis_screen

    install_analysis_screen(
        app,
        analysis_provider=app._build_ai_analysis_text,
        home_handler=app._operator_home_handler,
    )
