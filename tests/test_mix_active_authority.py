import json
import tempfile
import unittest
from pathlib import Path

from mix_active_authority import MixActiveAuthorityError, MixActiveTimeAuthority


class Clock:
    def __init__(self, value):
        self.value = float(value)

    def __call__(self):
        return self.value


class MixActiveTimeAuthorityTests(unittest.TestCase):
    def _store(self, root, mono, wall):
        return MixActiveTimeAuthority(
            Path(root) / "mix.json",
            monotonic=mono,
            wall_time=wall,
        )

    def test_active_time_advances_only_while_active(self):
        with tempfile.TemporaryDirectory() as tmp:
            mono = Clock(100.0)
            wall = Clock(1000.0)
            store = self._store(tmp, mono, wall)
            store.begin("s1", active=True)

            mono.value += 30.0
            wall.value += 30.0
            self.assertAlmostEqual(store.observe("s1", active=True).elapsed_s, 30.0)

            mono.value += 10.0
            wall.value += 10.0
            self.assertAlmostEqual(store.observe("s1", active=False).elapsed_s, 40.0)

            mono.value += 600.0
            wall.value += 600.0
            self.assertAlmostEqual(store.observe("s1", active=False).elapsed_s, 40.0)

            mono.value += 5.0
            wall.value += 5.0
            store.observe("s1", active=True)
            mono.value += 20.0
            wall.value += 20.0
            self.assertAlmostEqual(store.observe("s1", active=True).elapsed_s, 60.0)

    def test_restart_while_active_conservatively_charges_downtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            mono = Clock(100.0)
            wall = Clock(1000.0)
            first = self._store(tmp, mono, wall)
            first.begin("s1", active=True)
            mono.value += 30.0
            wall.value += 30.0
            first.observe("s1", active=True)

            # New process: monotonic epoch is unrelated. Durable active=True means
            # uncertain downtime is conservatively counted, never granted for free.
            mono2 = Clock(5.0)
            wall2 = Clock(1090.0)
            restored = self._store(tmp, mono2, wall2)
            self.assertAlmostEqual(restored.load("s1").elapsed_s, 30.0)
            snap = restored.observe("s1", active=True)
            self.assertAlmostEqual(snap.elapsed_s, 90.0)

    def test_restart_while_inactive_does_not_spend_mix_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            mono = Clock(100.0)
            wall = Clock(1000.0)
            first = self._store(tmp, mono, wall)
            first.begin("s1", active=True)
            mono.value += 30.0
            wall.value += 30.0
            first.observe("s1", active=False)

            mono2 = Clock(5.0)
            wall2 = Clock(100000.0)
            restored = self._store(tmp, mono2, wall2)
            restored.load("s1")
            snap = restored.observe("s1", active=False)
            self.assertAlmostEqual(snap.elapsed_s, 30.0)

    def test_missing_or_wrong_session_never_reconstructs_from_other_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            mono = Clock(1.0)
            wall = Clock(1000.0)
            store = self._store(tmp, mono, wall)
            with self.assertRaises(MixActiveAuthorityError):
                store.load("missing")
            store.begin("s1")
            other = self._store(tmp, Clock(2.0), Clock(1001.0))
            with self.assertRaisesRegex(MixActiveAuthorityError, "session mismatch"):
                other.load("s2")

    def test_corrupt_durable_record_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "mix.json"
            path.write_text('{"version": 1, "session_id": "s1", "elapsed_s": -1}', encoding="utf-8")
            store = MixActiveTimeAuthority(path, monotonic=Clock(1.0), wall_time=Clock(1000.0))
            with self.assertRaises(MixActiveAuthorityError):
                store.load("s1")

    def test_terminal_reason_and_elapsed_survive_reconstruction(self):
        with tempfile.TemporaryDirectory() as tmp:
            mono = Clock(10.0)
            wall = Clock(1000.0)
            store = self._store(tmp, mono, wall)
            store.begin("s1", active=True)
            mono.value += 12.0
            wall.value += 12.0
            terminal = store.mark_terminal("s1", "MIX_TIMEOUT")
            self.assertAlmostEqual(terminal.elapsed_s, 12.0)
            self.assertFalse(terminal.active)

            raw = json.loads((Path(tmp) / "mix.json").read_text(encoding="utf-8"))
            self.assertEqual(raw["terminal_reason"], "MIX_TIMEOUT")
            restored = self._store(tmp, Clock(1.0), Clock(5000.0)).load("s1")
            self.assertEqual(restored.terminal_reason, "MIX_TIMEOUT")
            self.assertAlmostEqual(restored.elapsed_s, 12.0)


if __name__ == "__main__":
    unittest.main()
