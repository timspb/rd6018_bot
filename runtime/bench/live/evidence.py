from __future__ import annotations

from .models import PhysicalSnapshotEvidence


class LiveEvidenceRecorder:
    def __init__(self):
        self.records: list[PhysicalSnapshotEvidence] = []

    def save(self, evidence: PhysicalSnapshotEvidence) -> PhysicalSnapshotEvidence:
        self.records.append(evidence)
        return evidence

