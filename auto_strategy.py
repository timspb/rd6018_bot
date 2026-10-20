"""Compatibility import for the former AUTO presentation subclass.

AUTO presentation now runs through application owners on the canonical host.
"""

from production_controller import ProductionChargeController


class AutoStrategyProductionChargeController(ProductionChargeController):
    """Compatibility name; AUTO presentation methods live in application owners."""
