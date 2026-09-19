"""Compatibility import for the single canonical generic V3 engine."""

from .generic import GenericChargeEngine

ChargeEngine = GenericChargeEngine

__all__ = ["ChargeEngine"]
