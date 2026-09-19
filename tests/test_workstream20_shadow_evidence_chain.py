import unittest

from application.shadow_evidence_chain import EvidenceGap, ShadowEvidenceChainValidator
from v3_core.canonical_events import CanonicalChargeEvent, EventSource, EventType
from v3_core.shadow_runtime_evidence import ShadowEvidenceBundle, ShadowReplayEngine


def chain(*, complete=True, session="s", trace="t"):
    kinds = [
        EventType.SESSION_STARTED, EventType.PHASE_STARTED, EventType.PHASE_TRANSITION,
        EventType.DELTA_STARTED, EventType.DELTA_COMPLETED, EventType.HOLD_STARTED,
        EventType.HOLD_COMPLETED, EventType.TERMINATION_DETECTED, EventType.SESSION_STOPPED,
    ]
    if not complete:
        kinds.remove(EventType.HOLD_COMPLETED)
    return tuple(CanonicalChargeEvent(str(i), float(i), session, trace, EventSource.DOMAIN, kind, metadata={"telemetry_ref": f"tel-{i}"}) for i, kind in enumerate(kinds, 1))


class Workstream20ShadowEvidenceChainTests(unittest.TestCase):
    def test_complete_chain_and_ordering(self):
        result = ShadowEvidenceChainValidator().validate(chain(), session_id="s")
        self.assertTrue(result.complete)
        self.assertTrue(result.replay_safe)
        self.assertEqual(9, len(result.ordered_event_types))

    def test_incomplete_chain_classifies_missing_event(self):
        result = ShadowEvidenceChainValidator().validate(chain(complete=False), session_id="s")
        self.assertFalse(result.complete)
        self.assertIn(EvidenceGap.MISSING_EVENT, {gap.category for gap in result.gaps})

    def test_missing_telemetry_correlation_is_blocking(self):
        events = list(chain())
        events[0] = CanonicalChargeEvent("1", 1.0, "s", "t", EventSource.DOMAIN, EventType.SESSION_STARTED)
        result = ShadowEvidenceChainValidator().validate(events, session_id="s")
        self.assertIn(EvidenceGap.MISSING_SOURCE, {gap.category for gap in result.gaps})

    def test_replay_is_read_only_and_session_isolated(self):
        bundle = ShadowEvidenceBundle("e", "o", "s", "t", 20.0, events=chain(), current_phase="mix", session_state="active")
        replay = ShadowReplayEngine().replay(bundle)
        self.assertFalse(replay.execution_performed)
        self.assertEqual("s", replay.reconstructed_timeline.session_id)
        foreign = chain(session="foreign")
        filtered = ShadowEvidenceChainValidator().validate(foreign, session_id="s")
        self.assertFalse(filtered.complete)

    def test_ui_reset_contract_remains_session_scoped(self):
        from v3_core.ui_session import SessionTimeline
        timeline = SessionTimeline()
        first = timeline.start(started_at=1)
        timeline.graph = timeline.graph.append(type(timeline.graph.samples[0])(1, 14.0, 1.0, 14.0, 23.0)) if timeline.graph.samples else timeline.graph
        second = timeline.start(started_at=2)
        self.assertNotEqual(first.session_id, second.session_id)
        self.assertEqual(0, len(timeline.graph.samples))


if __name__ == "__main__":
    unittest.main()
