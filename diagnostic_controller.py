from __future__ import annotations

"""Compatibility import for the canonical production charge host.

Diagnostic lifecycle is application/runtime owned; this name is retained only
for old imports and is not a subclass or production host.
"""

from production_controller import ProductionChargeController

DiagnosticProductionChargeController = ProductionChargeController
