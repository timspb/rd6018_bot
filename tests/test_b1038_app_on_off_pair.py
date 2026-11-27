from __future__ import annotations

import unittest

from runtime.output.command_receipt import OutputCommandReceipt
from tools.b1038_app_on_off_pair import PairEvidenceError, pair_execution_port_callbacks


class SensorInfo:
    def __init__(self, key: int, device_id: int = 4):
        self.key, self.device_id, self.object_id = key, device_id, f"entity_{key}"


class SensorState:
    def __init__(self, key: int, state):
        self.key, self.state = key, state


def callback(target: bool, request_id: str, terminal: float, stamp: float, *,
             transport=None, client=None, device=4, generation=2, include_r18=True,
             volts=None, amps=None):
    transport = transport if transport is not None else object()
    client = client if client is not None else object()
    receipt = OutputCommandReceipt(request_id, target, "APPLIED", int(target),
                                   terminal, generation, "raw terminal")
    records = {}
    values = {"output_r18": int(target),
              "voltage_v": (13.1 if target else 0.0) if volts is None else volts,
              "current_a": (1.2 if target else 0.0) if amps is None else amps}
    for key, field in enumerate(("output_r18", "voltage_v", "current_a"), 1):
        if field == "output_r18" and not include_r18:
            continue
        sensor_info = SensorInfo(key, device)
        state = SensorState(key, values[field])
        records[field] = {
            "sensor_info": sensor_info, "state": state, "value": values[field],
            "object_id": sensor_info.object_id, "key": key,
            "device_id": device, "native_type": "SensorState", "source": "esp_native_api",
            "status": "ok", "subscription_timestamp_monotonic": stamp + (key * 0.01),
            "age_s": 0.2, "connection_generation": generation,
        }
    return (receipt, {"status": "OBSERVED", "records": records,
                      "source_transport": transport, "source_client": client}), transport, client


class B1038AppOnOffPairTests(unittest.TestCase):
    def good_pair(self):
        transport, client = object(), object()
        on, _, _ = callback(True, "on-exact", 10.0, 10.1,
                            transport=transport, client=client)
        off, _, _ = callback(False, "off-exact", 14.0, 14.1,
                             transport=transport, client=client)
        return on, off, transport, client

    def pair(self, on, off, now=14.5):
        return pair_execution_port_callbacks(on_callback=on, off_callback=off,
                                             now_monotonic=now)

    def test_actual_callback_values_pair_once_and_remain_source_only(self):
        on, off, transport, client = self.good_pair()
        result = self.pair(on, off)
        self.assertEqual(result["status"], "SOURCE_PAIR_CONSISTENT")
        self.assertEqual(result["physical_p3_status"], "NOT_ESTABLISHED_SOURCE_ONLY")
        self.assertEqual(result["same_transport_client_status"], "SAME_OBJECTS")
        self.assertEqual((result["on_request_id"], result["off_request_id"]),
                         ("on-exact", "off-exact"))
        self.assertIs(on[1]["source_transport"], transport)
        self.assertIs(off[1]["source_client"], client)

    def test_same_generation_but_distinct_clients_is_rejected(self):
        on, _, transport, _ = self.good_pair()
        off, _, _ = callback(False, "off", 14.0, 14.1, transport=transport,
                             client=object(), generation=2)
        with self.assertRaisesRegex(PairEvidenceError, "different transport/client"):
            self.pair(on, off)

    def test_same_generation_but_distinct_transports_is_rejected(self):
        on, off, _, client = self.good_pair()
        off = callback(False, "off", 14.0, 14.1, transport=object(), client=client)[0]
        with self.assertRaisesRegex(PairEvidenceError, "different transport/client"):
            self.pair(on, off)

    def test_preterminal_and_stale_callbacks_are_rejected(self):
        on, off, transport, client = self.good_pair()
        old_on = callback(True, "on", 10.2, 10.0, transport=transport, client=client)[0]
        with self.assertRaisesRegex(PairEvidenceError, "preterminal"):
            self.pair(old_on, off)
        with self.assertRaisesRegex(PairEvidenceError, "stale"):
            self.pair(on, off, now=23.0)

    def test_missing_r18_callback_is_rejected(self):
        on, _, transport, client = self.good_pair()
        off = callback(False, "off", 14.0, 14.1, transport=transport,
                       client=client, include_r18=False)[0]
        with self.assertRaisesRegex(PairEvidenceError, "field missing"):
            self.pair(on, off)

    def test_nonzero_post_off_voltage_or_current_is_rejected(self):
        on, _, transport, client = self.good_pair()
        for kwargs in ({"volts": 0.01}, {"amps": -0.01}):
            off = callback(False, "off", 14.0, 14.1, transport=transport,
                           client=client, **kwargs)[0]
            with self.subTest(kwargs=kwargs), self.assertRaisesRegex(
                    PairEvidenceError, "must be zero"):
                self.pair(on, off)

    def test_cross_device_pair_is_rejected(self):
        on, _, transport, client = self.good_pair()
        off = callback(False, "off", 14.0, 14.1, transport=transport,
                       client=client, device=5)[0]
        with self.assertRaisesRegex(PairEvidenceError, "different ESP devices"):
            self.pair(on, off)

    def test_missing_or_unobserved_callbacks_are_rejected(self):
        on, off, _, _ = self.good_pair()
        for candidate in (None, (off[0], {"status": "NOT_OBSERVED"})):
            with self.subTest(candidate=candidate), self.assertRaises(PairEvidenceError):
                self.pair(on, candidate)


if __name__ == "__main__":
    unittest.main()
