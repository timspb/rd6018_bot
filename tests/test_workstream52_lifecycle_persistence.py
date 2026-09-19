import unittest

from application.charge_lifecycle import (
    ChargeLifecycleSnapshot, DeltaState, HoldState, LifecycleEvent,
    LifecycleEventType, LifecycleRestoreClassifier, RestoreKind, SafetyState,
    TelemetryContinuityGuard, TelemetryState, validate_event_continuity,
)


def snapshot():
    return ChargeLifecycleSnapshot(
        "s-1", "battery-1", "program-1", "HOLD", 10.0, ("delta-complete",),
        DeltaState("COMPLETED", 2.0, 8.0, ("voltage", "current")),
        HoldState("ACTIVE", 8.0, 12.0, ("fresh telemetry",)),
        SafetyState("NORMAL", verification="FRESH"), 22.0, "t-1",
    )


class LifecyclePersistenceTests(unittest.TestCase):
    def test_snapshot_round_trip_is_immutable(self):
        value = snapshot()
        self.assertEqual(value.current_phase, "HOLD")
        with self.assertRaises(AttributeError):
            value.current_phase = "DONE"

    def test_resume_existing_requires_identity(self):
        classifier = LifecycleRestoreClassifier()
        result = classifier.classify(snapshot())
        self.assertEqual(result.kind, RestoreKind.RESUME_EXISTING)

    def test_legacy_state_is_ambiguous_and_new_is_start_new(self):
        classifier = LifecycleRestoreClassifier()
        self.assertEqual(classifier.classify(None, legacy_state={"phase": "HOLD"}).kind, RestoreKind.AMBIGUOUS)
        self.assertEqual(classifier.classify(None).kind, RestoreKind.START_NEW)

    def test_stale_telemetry_does_not_jump_phase(self):
        guard = TelemetryContinuityGuard()
        self.assertEqual(guard.evaluate("MIX", TelemetryState.STALE, "HOLD"), "MIX")
        self.assertEqual(guard.evaluate("MIX", TelemetryState.RECOVERED, "HOLD"), "HOLD")

    def test_hold_delta_event_continuity(self):
        events = tuple(LifecycleEvent(kind, "s-1", "t-1", index) for index, kind in enumerate((LifecycleEventType.SESSION, LifecycleEventType.PHASE, LifecycleEventType.DELTA, LifecycleEventType.HOLD)))
        self.assertEqual(validate_event_continuity(events, "s-1", "t-1")[0], True)
        self.assertEqual(validate_event_continuity(events, "s-2", "t-1")[0], False)


if __name__ == "__main__":
    unittest.main()
