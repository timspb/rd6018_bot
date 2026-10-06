from __future__ import annotations

import time
from typing import Any

from runtime.config import ConfigBundle
from runtime.output.bridge import HardwareSnapshot
from runtime.physical.transports import PhysicalSnapshotComparator, PhysicalTransportFactory

from .evidence import LiveEvidenceRecorder
from .models import LiveSnapshotRun, PhysicalSnapshotEvidence


_REQUIRED_LIVE_FIELDS = (
    "output_state",
    "measured_voltage",
    "measured_current",
    "configured_voltage",
    "configured_current",
    "ovp",
    "ocp",
    "temperature",
    "battery_voltage",
)


def _snapshot_quality(snapshot: HardwareSnapshot) -> tuple[str, tuple[str, ...]]:
    errors: list[str] = []
    if snapshot.connection_state != "connected":
        errors.append(f"connection_state:{snapshot.connection_state or 'missing'}")
    missing = [name for name in _REQUIRED_LIVE_FIELDS if getattr(snapshot, name) is None]
    if missing:
        errors.append("missing_fields:" + ",".join(missing))
    return ("VALID", ()) if not errors else ("INVALID", tuple(errors))


class LiveSmokeRunner:
    """Read-only live runner; it has no command or executor dependency."""

    def __init__(self, config: ConfigBundle, *, recorder: LiveEvidenceRecorder | None = None):
        self.config = config
        self.recorder = recorder or LiveEvidenceRecorder()

    async def run(self, operator: str = "live-smoke") -> PhysicalSnapshotEvidence:
        factory = PhysicalTransportFactory(self.config)
        runs = []
        snapshots = {}
        for name in ("ha102", "esp128"):
            transport = factory.create(name)
            try:
                await transport.discover()
                snapshot = await transport.get_snapshot()
                await transport.get_capabilities()
                await transport.health_check()
                quality, errors = _snapshot_quality(snapshot)
                runs.append(LiveSnapshotRun(time.time(), name, name, snapshot, quality, errors))
                snapshots[name] = snapshot
            except Exception as exc:
                runs.append(LiveSnapshotRun(time.time(), name, name, None, "ERROR", (f"{type(exc).__name__}: {exc}",)))
            finally:
                close = getattr(transport, "close", None)
                if close is not None:
                    await close()
        comparison = PhysicalSnapshotComparator.compare(
            snapshots.get("ha102"), snapshots.get("esp128"),
            tolerance=float(self.config.runtime.get("snapshot_voltage_tolerance_v", 0.06)),
            timestamp_tolerance=float(self.config.runtime.get("snapshot_timestamp_tolerance_s", 10)),
            current_tolerance=float(self.config.runtime.get("snapshot_current_tolerance_a", 0.06)),
        )
        evidence = PhysicalSnapshotEvidence(
            time.time(), operator, snapshots.get("ha102"), snapshots.get("esp128"), comparison, tuple(runs)
        )
        return self.recorder.save(evidence)
