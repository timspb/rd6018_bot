from __future__ import annotations

import time
from typing import Any

from runtime.config import ConfigBundle
from runtime.physical.transports import PhysicalSnapshotComparator, PhysicalTransportFactory

from .evidence import LiveEvidenceRecorder
from .models import LiveSnapshotRun, PhysicalSnapshotEvidence


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
                discovered = await transport.discover()
                snapshot = await transport.get_snapshot()
                await transport.get_capabilities()
                await transport.health_check()
                runs.append(LiveSnapshotRun(time.time(), name, name, snapshot, "VALID" if snapshot.connection_state == "connected" else "INVALID"))
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
        evidence = PhysicalSnapshotEvidence(time.time(), operator, snapshots.get("ha102"), snapshots.get("esp128"), comparison, tuple(runs))
        return self.recorder.save(evidence)
