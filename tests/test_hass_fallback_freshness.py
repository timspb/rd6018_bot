import unittest
from datetime import datetime
from unittest.mock import AsyncMock, patch

from config import ENTITY_MAP
from hass_api import HassClient
from rd6018_telemetry import telemetry_freshness


class _FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status = status

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def json(self):
        return self._payload


class _FakeSession:
    def __init__(self, payload):
        self._payload = payload

    def get(self, _url):
        return _FakeResponse(self._payload)


class HassFallbackFreshnessTests(unittest.IsolatedAsyncioTestCase):
    def test_entity_metadata_age_prefers_last_reported_over_last_updated(self):
        reported = "2026-08-30T14:33:05+00:00"
        updated = "2026-01-01T00:00:00+00:00"
        now = datetime.fromisoformat("2026-08-30T14:33:10+00:00").timestamp()
        with patch("hass_api.time.time", return_value=now):
            meta = HassClient._entity_metadata(
                "sensor.test",
                {
                    "last_reported": reported,
                    "last_updated": updated,
                    "last_changed": updated,
                },
                "ok",
            )
        self.assertEqual(meta["last_reported"], reported)
        self.assertEqual(meta["last_updated"], updated)
        self.assertAlmostEqual(meta["age_s"], 5.0, places=3)

    async def test_get_state_preserves_top_level_last_reported(self):
        payload = {
            "state": "12.6",
            "attributes": {"unit_of_measurement": "V"},
            "last_reported": "2026-08-30T14:33:05+00:00",
            "last_updated": "2026-01-01T00:00:00+00:00",
            "last_changed": "2026-01-01T00:00:00+00:00",
        }
        client = HassClient("http://127.0.0.1:8123", "token")
        client._ensure_session = AsyncMock(return_value=_FakeSession(payload))

        state, attrs = await client.get_state("sensor.test")

        self.assertEqual(state, 12.6)
        self.assertEqual(attrs["_ha_last_reported"], payload["last_reported"])
        self.assertEqual(attrs["_ha_last_updated"], payload["last_updated"])
        self.assertEqual(attrs["_ha_last_changed"], payload["last_changed"])

    async def test_fallback_get_all_live_keeps_last_reported_as_freshness_heartbeat(self):
        reported = "2026-08-30T14:33:05+00:00"
        updated = "2026-01-01T00:00:00+00:00"
        now = datetime.fromisoformat("2026-08-30T14:33:10+00:00").timestamp()

        client = HassClient("http://127.0.0.1:8123", "token")
        client._live_keys = lambda: ["battery_voltage"]
        client._fetch_all_states_bulk = AsyncMock(return_value=None)
        client.get_state = AsyncMock(
            return_value=(
                12.6,
                {
                    "_ha_last_reported": reported,
                    "_ha_last_updated": updated,
                    "_ha_last_changed": updated,
                },
            )
        )

        live = await client.get_all_live()
        meta = live["_meta"]["battery_voltage"]

        self.assertEqual(meta["last_reported"], reported)
        self.assertEqual(meta["last_updated"], updated)
        freshness = telemetry_freshness(
            live,
            ["battery_voltage"],
            max_age_s=20.0,
            now_epoch_s=now,
        )
        self.assertTrue(freshness.valid, freshness.detail)

    async def test_fallback_without_last_reported_still_uses_last_updated_compatibly(self):
        updated = "2026-08-30T14:33:05+00:00"
        now = datetime.fromisoformat("2026-08-30T14:33:10+00:00").timestamp()

        client = HassClient("http://127.0.0.1:8123", "token")
        client._live_keys = lambda: ["battery_voltage"]
        client._fetch_all_states_bulk = AsyncMock(return_value=None)
        client.get_state = AsyncMock(
            return_value=(
                12.6,
                {
                    "_ha_last_reported": None,
                    "_ha_last_updated": updated,
                    "_ha_last_changed": updated,
                },
            )
        )

        live = await client.get_all_live()
        freshness = telemetry_freshness(
            live,
            ["battery_voltage"],
            max_age_s=20.0,
            now_epoch_s=now,
        )
        self.assertTrue(freshness.valid, freshness.detail)

    async def test_bulk_failure_uses_one_batched_get_states_call(self):
        reported = "2026-08-30T14:33:05+00:00"
        attrs = {
            "_ha_last_reported": reported,
            "_ha_last_updated": reported,
            "_ha_last_changed": reported,
        }
        client = HassClient("http://127.0.0.1:8123", "token")
        client._live_keys = lambda: ["battery_voltage", "current"]
        client._fetch_all_states_bulk = AsyncMock(return_value=None)
        client.get_states = AsyncMock(
            return_value={
                ENTITY_MAP["battery_voltage"]: (12.6, dict(attrs)),
                ENTITY_MAP["current"]: (1.2, dict(attrs)),
            }
        )

        live = await client.get_all_live()

        client.get_states.assert_awaited_once_with(
            [ENTITY_MAP["battery_voltage"], ENTITY_MAP["current"]]
        )
        self.assertEqual(live["battery_voltage"], 12.6)
        self.assertEqual(live["current"], 1.2)


if __name__ == "__main__":
    unittest.main()
