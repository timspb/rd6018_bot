import json
import os
import tempfile
import unittest
from unittest.mock import patch

from runtime.operator.pause_state import OperatorPauseState


class OperatorPauseStateTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tempdir.name, "operator_pause_state.json")

    def tearDown(self):
        self.tempdir.cleanup()

    def test_roundtrip_preserves_legacy_document_and_timestamp(self):
        state = OperatorPauseState(1731412345.25)
        self.assertTrue(state.active())
        self.assertEqual(state.to_document(), {"started_at": 1731412345.25})
        state.save(self.path)
        with open(self.path, encoding="utf-8") as stream:
            self.assertEqual(json.load(stream), {"started_at": 1731412345.25})
        self.assertEqual(OperatorPauseState.load(self.path).started_at, 1731412345.25)

    def test_invalid_documents_unarm(self):
        invalid = (
            "{", "[]", "null", "{}", '{"started_at": true}',
            '{"started_at": "123.0"}', '{"started_at": NaN}',
            '{"started_at": Infinity}', '{"started_at": 0}',
            '{"started_at": -1}',
        )
        for document in invalid:
            with self.subTest(document=document):
                with open(self.path, "w", encoding="utf-8") as stream:
                    stream.write(document)
                self.assertFalse(OperatorPauseState.load(self.path).active())

    def test_missing_file_is_unpaused_and_clearing_prevents_resurrection(self):
        self.assertFalse(OperatorPauseState.load(self.path).active())
        with open(self.path, "w", encoding="utf-8") as stream:
            json.dump({"started_at": 123.0}, stream)
        state = OperatorPauseState.load(self.path)
        state.clear(self.path)
        self.assertFalse(state.active())
        self.assertFalse(os.path.exists(self.path))
        self.assertFalse(OperatorPauseState.load(self.path).active())

    def test_save_uses_atomic_replace_and_fsync(self):
        state = OperatorPauseState(123.0)
        real_replace = os.replace
        with patch("runtime.operator.pause_state.os.fsync", wraps=os.fsync) as fsync, \
                patch("runtime.operator.pause_state.os.replace", wraps=real_replace) as replace:
            state.save(self.path)
        fsync.assert_called_once()
        replace.assert_called_once()
        self.assertEqual(replace.call_args.args[1], self.path)
        self.assertTrue(os.path.exists(self.path))
        self.assertEqual(os.listdir(self.tempdir.name), ["operator_pause_state.json"])

    def test_empty_save_removes_only_supplied_sidecar(self):
        with open(self.path, "w", encoding="utf-8") as stream:
            stream.write('{"started_at": 123}')
        other = os.path.join(self.tempdir.name, "unrelated.json")
        with open(other, "w", encoding="utf-8") as stream:
            stream.write("{}")
        OperatorPauseState().save(self.path)
        self.assertFalse(os.path.exists(self.path))
        self.assertTrue(os.path.exists(other))

    def test_failed_save_propagates_and_failed_clear_preserves_memory(self):
        state = OperatorPauseState(123.0)
        with patch("runtime.operator.pause_state.os.replace", side_effect=OSError("disk")):
            with self.assertRaises(OSError):
                state.save(os.path.join(self.tempdir.name, "missing", "pause.json"))
        self.assertEqual(state.started_at, 123.0)

        state = OperatorPauseState(123.0)
        with patch("runtime.operator.pause_state.os.remove", side_effect=OSError("disk")):
            with self.assertRaises(OSError):
                state.clear(self.path)
        self.assertEqual(state.started_at, 123.0)

    def test_clear_missing_file_is_successful_and_idempotent(self):
        state = OperatorPauseState(123.0)
        self.assertTrue(state.clear(self.path))
        self.assertFalse(state.active())

    def test_state_has_no_physical_side_effects_or_global_instance(self):
        self.assertFalse(any(callable(getattr(OperatorPauseState, name, None))
                             for name in ("turn_on", "turn_off", "set_voltage", "set_current")))
        import runtime.operator.pause_state as module
        self.assertFalse(any(isinstance(value, OperatorPauseState)
                             for value in vars(module).values()))


if __name__ == "__main__":
    unittest.main()
