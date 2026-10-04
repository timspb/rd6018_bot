"""Canonical modular screen builders."""

from .details import build_operator_details_screen, operator_details_button_spec
from .journal import build_journal_screen, journal_button_spec

__all__ = [
    "build_journal_screen",
    "build_operator_details_screen",
    "journal_button_spec",
    "operator_details_button_spec",
]
