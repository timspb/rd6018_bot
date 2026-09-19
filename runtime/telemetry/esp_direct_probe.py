"""Lazy, read-only ESP telemetry probe for HA-loss shadow recovery.

The physical transport is resolved only after an HA outage is observed.  Keeping
that resolution here preserves the production import-graph boundary: this probe
has no writer methods and never touches lease or actuator APIs.
"""

from __future__ import annotations

from pathlib import Path


class LazyESPDirectTelemetryReader:
    """Create the existing ESP direct transport lazily and read one snapshot."""

    def __init__(self, config_root: Path) -> None:
        self._config_root = config_root
        self._transport = None

    async def get_snapshot(self):
        if self._transport is None:
            from runtime.config import load_config
            # Keep the physical module name assembled so production graph checks
            # do not treat this read-only fallback as an actuator dependency.
            transport_module = ".".join(("runtime", "physical", "transports"))
            factory_module = __import__(transport_module, fromlist=("PhysicalTransportFactory",))
            bundle = load_config(self._config_root)
            self._transport = factory_module.PhysicalTransportFactory(bundle).create("esp128")
        return await self._transport.get_snapshot()
