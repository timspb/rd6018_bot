"""Data-only safety state vocabulary for Phase 2 contract normalization."""

from __future__ import annotations

from enum import Enum


class SafetyState(str, Enum):
    NORMAL = "normal"
    DEGRADED = "degraded"
    CONTAINMENT = "containment"
    OFF_CONFIRMED = "off_confirmed"
    OFF_UNCONFIRMED = "off_unconfirmed"
    LATCHED = "latched"

