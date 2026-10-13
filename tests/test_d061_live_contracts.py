"""Regression against actual HA sensor shape and persisted Leoch chemistry enum."""
import sqlite3
import unittest
from datetime import datetime, timezone

from tools.acceptance_guard.takeover import select_leoch_battery, independent_output_off


class LeochRegistryTests(unittest.TestCase):
    def test_ca_ca_enum_and_unique_match(self):
        db = sqlite3.connect(':memory:')
        try:
            db.execute('CREATE TABLE batteries (battery_id TEXT, manufacturer TEXT, model TEXT, chemistry TEXT, nominal_capacity_ah REAL)')
            db.execute('INSERT INTO batteries VALUES (?,?,?,?,?)', ('Leoch_72Ah', 'Leoch', '', 'ca_ca', 72.0))
            self.assertEqual(select_leoch_battery(db, 'Leoch_72Ah'), 'Leoch_72Ah')
            with self.assertRaisesRegex(RuntimeError, 'exactly one'):
                select_leoch_battery(db, 'unknown')
            db.execute('INSERT INTO batteries VALUES (?,?,?,?,?)', ('other', 'Leoch', 'Leoch_72Ah', 'ca_ca', 72.0))
            with self.assertRaisesRegex(RuntimeError, 'exactly one'):
                select_leoch_battery(db, 'Leoch_72Ah')
        finally:
            db.close()


class NumericOutputTests(unittest.IsolatedAsyncioTestCase):
    async def test_numeric_zero_is_off_and_unavailable_is_not(self):
        import time
        wall, mono = time.time(), time.monotonic()
        stamp = datetime.fromtimestamp(wall - 1, timezone.utc).isoformat()

        class HA:
            value = '0.0'
            async def _get(self, _entity):
                return {'state': self.value, 'last_reported': stamp}

        class ESP:
            async def get_physical_output_report(self):
                return 0.0, {'status': 'ok', 'native_type': 'SensorState',
                    'age_s': 1.0, 'subscription_timestamp_monotonic': mono}

        args = {'wall_time': lambda: wall, 'monotonic': lambda: mono}
        ha = HA()
        self.assertTrue(await independent_output_off(ha, ESP(), 'sensor.output', **args))
        for invalid in ('off', 'unavailable', 'unknown', 'nan', '1', '1.0'):
            ha.value = invalid
            self.assertFalse(await independent_output_off(ha, ESP(), 'sensor.output', **args))
        ha.value = 'off'
        self.assertTrue(await independent_output_off(ha, ESP(), 'switch.output', **args))
