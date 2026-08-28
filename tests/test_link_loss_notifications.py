import unittest
from unittest.mock import patch

from charge_logic import ChargeController


class DummyHass:
    pass


class LinkLossNotificationTests(unittest.IsolatedAsyncioTestCase):
    async def test_link_loss_notifications_are_rate_limited(self):
        messages = []
        controller = ChargeController(DummyHass(), notify_cb=messages.append)
        controller.current_stage = controller.STAGE_MAIN
        controller._last_known_output_on = True
        now = [1000.0]

        # Patch time with a stable clock value rather than a finite side_effect
        # iterator. charge_logic imports the shared time module, so logging calls
        # may also observe time.time() and must not consume test timestamps.
        with patch("charge_logic.time.time", side_effect=lambda: now[0]):
            for timestamp in (1000.0, 1060.0, 1120.0, 4720.0):
                now[0] = timestamp
                await controller.tick(
                    voltage=14.3,
                    current=0.7,
                    temp_ext=None,
                    is_cv=True,
                    ah=10.0,
                    output_is_on=True,
                )

        self.assertEqual(len(messages), 3)
        self.assertTrue(all("Связь потеряна во время заряда!" in msg for msg in messages))


if __name__ == "__main__":
    unittest.main()
