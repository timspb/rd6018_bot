"""Regressions for D106 false callback/cache mismatch when a later native update arrives."""
import unittest

from tools.node104_d106_live_observer import _validate_callback_cache_generation
from tools.node104_d106_live_observer import ro as _ro
ProofError = _ro.ProofError


class CallbackCacheGenerationTests(unittest.TestCase):
    def sample(self, *, original_value=0.0, current_value=0.0,
               callback_ts=100.0, cache_ts=100.001, key=12,
               cache_type="SensorState", object_id="output_state"):
        callback=(original_value,{
            "source":"esp_native_api", "native_type":"SensorState",
            "object_id":"output_state", "key":12, "device_id":0,
            "subscription_timestamp_monotonic":callback_ts,
        })
        cached={"value":current_value,"meta":{
            "source":"esp_native_api","native_type":cache_type,
            "actual_object_id":object_id,"native_key":key,"device_id":0,
            "subscription_timestamp_monotonic":cache_ts,
        }}
        return callback,cached

    def test_exact_callback_generation_matching_value(self):
        _validate_callback_cache_generation("output_r18",*self.sample())

    def test_newer_native_update_can_legitimately_change_value(self):
        # Original collector waits 0.5 seconds between the first callback
        # and the later subscribed-state cache snapshot.
        _validate_callback_cache_generation("output_r18",*self.sample(
            original_value=1.0,current_value=0.0,cache_ts=100.5))

    def test_same_generation_with_different_value_still_rejected(self):
        with self.assertRaisesRegex(ProofError,"same-callback/cache disagreement"):
            _validate_callback_cache_generation("output_r18",*self.sample(
                original_value=1.0,current_value=0.0))

    def test_cache_older_than_proven_callback_rejected(self):
        with self.assertRaisesRegex(ProofError,"cache older"):
            _validate_callback_cache_generation("output_r18",*self.sample(
                cache_ts=99.5))

    def test_cache_must_match_original_native_entity_key(self):
        for kwargs in ({"key":999}, {"cache_type":"ButtonState"},
                       {"object_id":"another_sensor"}):
            with self.subTest(kwargs=kwargs):
                with self.assertRaisesRegex(ProofError,"identity or type"):
                    _validate_callback_cache_generation("output_r18",*self.sample(**kwargs))


if __name__ == "__main__":
    unittest.main()
