import unittest

from ha_history import (
    HistoryPoint,
    HomeAssistantHistoryReader,
    derive_continuous_on_evidence,
    summarize_numeric,
)


class FakeResponse:
    def __init__(self, payload, status=200):
        self.payload = payload
        self.status = status

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def json(self):
        return self.payload


class FakeSession:
    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.calls = []

    def get(self, url, params=None):
        self.calls.append((url, dict(params or {})))
        if not self.payloads:
            raise AssertionError("unexpected history request")
        return FakeResponse(self.payloads.pop(0))


class FakeHass:
    def __init__(self, payloads):
        self.base_url = "http://ha.local:8123"
        self.session = FakeSession(payloads)

    async def _ensure_session(self):
        return self.session


class HomeAssistantHistoryTests(unittest.IsolatedAsyncioTestCase):
    def test_explicit_off_on_edge_is_reliable(self):
        points = [
            HistoryPoint("switch.rd", "off", 100.0),
            HistoryPoint("switch.rd", "on", 200.0),
            HistoryPoint("switch.rd", "on", 300.0),
        ]
        evidence = derive_continuous_on_evidence(
            points,
            now_s=500.0,
            live_output_on=True,
        )
        self.assertTrue(evidence.reliable)
        self.assertEqual(evidence.started_at_s, 200.0)
        self.assertEqual(evidence.elapsed_s, 300.0)

    def test_window_that_starts_with_on_is_not_an_authoritative_age(self):
        evidence = derive_continuous_on_evidence(
            [HistoryPoint("switch.rd", "on", 100.0)],
            now_s=500.0,
            live_output_on=True,
        )
        self.assertFalse(evidence.reliable)
        self.assertIsNone(evidence.started_at_s)
        self.assertIn("no explicit", evidence.reason)

    def test_unknown_after_detected_edge_invalidates_age(self):
        evidence = derive_continuous_on_evidence(
            [
                HistoryPoint("switch.rd", "off", 100.0),
                HistoryPoint("switch.rd", "on", 200.0),
                HistoryPoint("switch.rd", "unavailable", 300.0),
                HistoryPoint("switch.rd", "on", 400.0),
            ],
            now_s=500.0,
            live_output_on=True,
        )
        self.assertFalse(evidence.reliable)
        self.assertEqual(evidence.started_at_s, 200.0)
        self.assertIn("unknown", evidence.reason)

    def test_numeric_summary_ignores_unavailable_values(self):
        summary = summarize_numeric(
            "sensor.current",
            [
                HistoryPoint("sensor.current", "0.88", 100.0),
                HistoryPoint("sensor.current", "unavailable", 200.0),
                HistoryPoint("sensor.current", "0.99", 300.0),
                HistoryPoint("sensor.current", "0.90", 400.0),
            ],
        )
        self.assertEqual(summary.count, 3)
        self.assertEqual(summary.first, 0.88)
        self.assertEqual(summary.minimum, 0.88)
        self.assertEqual(summary.maximum, 0.99)
        self.assertEqual(summary.latest, 0.90)

    async def test_reader_uses_output_edge_then_summarizes_current_session(self):
        switch_entity = "switch.rd"
        current_entity = "sensor.current"
        voltage_entity = "sensor.vout"
        temp_entity = "sensor.temp_v2"
        set_v_entity = "number.vset"
        set_i_entity = "number.iset"
        payloads = [
            [
                [
                    {"entity_id": switch_entity, "state": "off", "last_changed": "1970-01-01T00:01:40+00:00"},
                    {"entity_id": switch_entity, "state": "on", "last_changed": "1970-01-01T00:03:20+00:00"},
                ]
            ],
            [
                [
                    {"entity_id": current_entity, "state": "0.88", "last_changed": "1970-01-01T00:03:20+00:00"},
                    {"entity_id": current_entity, "state": "0.99", "last_changed": "1970-01-01T00:05:00+00:00"},
                    {"entity_id": current_entity, "state": "0.90", "last_changed": "1970-01-01T00:06:40+00:00"},
                ],
                [
                    {"entity_id": voltage_entity, "state": "16.55", "last_changed": "1970-01-01T00:03:20+00:00"},
                ],
                [
                    {"entity_id": temp_entity, "state": "26", "last_changed": "1970-01-01T00:03:20+00:00"},
                    {"entity_id": temp_entity, "state": "27", "last_changed": "1970-01-01T00:06:40+00:00"},
                ],
                [
                    {"entity_id": set_v_entity, "state": "16.55", "last_changed": "1970-01-01T00:03:20+00:00"},
                ],
                [
                    {"entity_id": set_i_entity, "state": "1.00", "last_changed": "1970-01-01T00:03:20+00:00"},
                ],
            ],
        ]
        hass = FakeHass(payloads)
        reader = HomeAssistantHistoryReader(
            hass,
            {
                "switch": switch_entity,
                "current": current_entity,
                "voltage": voltage_entity,
                "temp_ext_v2": temp_entity,
                "set_voltage": set_v_entity,
                "set_current": set_i_entity,
            },
        )

        evidence = await reader.read_mix_evidence(
            live={"switch": "on"},
            lookback_s=500.0,
            now_s=500.0,
        )

        self.assertTrue(evidence.output.reliable)
        self.assertEqual(evidence.output.started_at_s, 200.0)
        self.assertEqual(evidence.output.elapsed_s, 300.0)
        self.assertIsNotNone(evidence.current)
        self.assertEqual(evidence.current.minimum, 0.88)
        self.assertEqual(evidence.current.maximum, 0.99)
        self.assertEqual(evidence.current.latest, 0.90)
        self.assertIsNotNone(evidence.external_temperature)
        self.assertEqual(evidence.external_temperature.maximum, 27.0)
        self.assertEqual(len(hass.session.calls), 2)
        self.assertIn("/api/history/period/", hass.session.calls[0][0])
        self.assertEqual(hass.session.calls[0][1]["filter_entity_id"], switch_entity)
        self.assertEqual(hass.session.calls[1][1]["filter_entity_id"].split(",")[0], current_entity)


if __name__ == "__main__":
    unittest.main()
