import unittest

from runtime.output.command_receipt import OutputCommandReceipt
from tools.b1024_native_phase_evidence import EvidenceError, assemble_on_off_evidence


def receipt(target, request_id, completed, generation=7, *, status="APPLIED", observed=None):
    return OutputCommandReceipt(
        request_id, target, status, int(target) if observed is None else observed,
        completed, generation, "captured terminal receipt",
    )


def phase(target, stamp, *, generation=7, device=3, source="esp_native_api",
          native_type="SensorState", age=0.2):
    return {
        "output_r18": {"value": int(target), "meta": {
            "source": source, "native_type": native_type, "status": "ok",
            "device_id": device, "connection_generation": generation,
            "subscription_timestamp_monotonic": stamp, "age_s": age}},
        "voltage_v": {"value": 12.4 if target else 0.0, "meta": {
            "source": source, "native_type": native_type, "status": "ok",
            "device_id": device, "connection_generation": generation,
            "subscription_timestamp_monotonic": stamp + 0.01, "age_s": age}},
        "current_a": {"value": 1.2 if target else 0.0, "meta": {
            "source": source, "native_type": native_type, "status": "ok",
            "device_id": device, "connection_generation": generation,
            "subscription_timestamp_monotonic": stamp + 0.02, "age_s": age}},
    }


class B1024NativePhaseEvidenceTests(unittest.TestCase):
    def valid_args(self):
        return dict(on_receipt=receipt(True, "on-1", 10.0),
                    on_native=phase(True, 10.1),
                    off_receipt=receipt(False, "off-1", 14.0),
                    off_native=phase(False, 14.1), now_monotonic=14.5)

    def test_valid_native_phases_are_explicitly_not_causal_proof(self):
        result = assemble_on_off_evidence(**self.valid_args())
        self.assertEqual(result["status"], "NATIVE_PHASE_OBSERVATION_PASS")
        self.assertEqual(result["native_phase_observation_status"], "PASS")
        self.assertEqual(
            result["causal_on_off_proof_status"],
            "NOT_PROVEN_MISSING_TRANSPORT_SESSION_IDENTITY",
        )
        self.assertEqual(
            result["clock_domain_status"], "UNVERIFIED_MONOTONIC_CLOCK_DOMAIN")
        self.assertEqual(result["connection_generation"], 7)

    def test_equal_generation_and_device_do_not_prove_same_transport_client(self):
        # Distinct ESPHomeTransport instances both start their local counter at 1.
        args = self.valid_args()
        args["on_receipt"] = receipt(True, "on-1", 10.0, generation=1)
        args["on_native"] = phase(True, 10.1, generation=1, device=3)
        args["off_receipt"] = receipt(False, "off-1", 14.0, generation=1)
        args["off_native"] = phase(False, 14.1, generation=1, device=3)
        result = assemble_on_off_evidence(**args)
        self.assertEqual(
            result["causal_on_off_proof_status"],
            "NOT_PROVEN_MISSING_TRANSPORT_SESSION_IDENTITY",
        )

    def test_d106_style_matching_device_type_and_age_still_is_not_session_provenance(self):
        args = self.valid_args()
        # D106 opens a separate client; its phase envelope contains device/type,
        # age and a per-client generation, but no identity shared with the app.
        result = assemble_on_off_evidence(**args)
        self.assertEqual(result["device_id"], 3)
        self.assertEqual(
            result["native_phase_observation_status"], "PASS")
        self.assertNotEqual(result["causal_on_off_proof_status"], "PASS")

    def test_rejects_ha_cache_stale_precommand_and_wrong_type(self):
        for changes in ({"source": "ha102_rest"}, {"age": 8.1},
                        {"native_type": "NumberState"}):
            args = self.valid_args()
            args["on_native"] = phase(True, 10.1, **changes)
            with self.subTest(changes=changes), self.assertRaises(EvidenceError):
                assemble_on_off_evidence(**args)
        args = self.valid_args()
        args["on_native"] = phase(True, 9.9)
        with self.assertRaisesRegex(EvidenceError, "newer than command"):
            assemble_on_off_evidence(**args)

    def test_rejects_identity_generation_receipt_and_r18_mismatch(self):
        mutations = (
            ("off_native", phase(False, 14.1, generation=8)),
            ("off_native", phase(False, 14.1, device=4)),
            ("off_native", phase(False, 14.1) | {"output_r18": {
                "value": 1, "meta": phase(False, 14.1)["output_r18"]["meta"]}}),
        )
        for name, value in mutations:
            args = self.valid_args(); args[name] = value
            with self.subTest(name=name), self.assertRaises(EvidenceError):
                assemble_on_off_evidence(**args)
        args = self.valid_args()
        args["on_receipt"] = receipt(True, "", 10.0)
        with self.assertRaises(EvidenceError):
            assemble_on_off_evidence(**args)

    def test_rejects_nonzero_post_off_voltage_or_current_and_ambiguous_receipt(self):
        for field in ("voltage_v", "current_a"):
            args = self.valid_args()
            args["off_native"] = phase(False, 14.1)
            args["off_native"][field]["value"] = 0.01
            with self.subTest(field=field), self.assertRaisesRegex(EvidenceError, "must be zero"):
                assemble_on_off_evidence(**args)
        args = self.valid_args()
        args["off_receipt"] = receipt(False, "off-1", 14.0, status="OUTCOME_UNCERTAIN")
        with self.assertRaisesRegex(EvidenceError, "ambiguous"):
            assemble_on_off_evidence(**args)

    def test_rejects_overlapping_or_reordered_phase_receipts(self):
        args = self.valid_args()
        args["off_receipt"] = receipt(False, "off-1", 10.11)
        args["off_native"] = phase(False, 10.2)
        args["now_monotonic"] = 10.5
        with self.assertRaisesRegex(EvidenceError, "timestamps are not ordered"):
            assemble_on_off_evidence(**args)


if __name__ == "__main__":
    unittest.main()
