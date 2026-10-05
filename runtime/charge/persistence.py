"""Canonical charge-session persistence constants."""

from __future__ import annotations


SESSION_FILE = "charge_session.json"
SESSION_START_MAX_AGE_S = 24 * 60 * 60


__all__ = ["SESSION_FILE", "SESSION_START_MAX_AGE_S"]
