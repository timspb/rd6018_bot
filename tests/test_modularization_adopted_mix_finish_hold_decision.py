"""Pure adopted-MIX finish-hold boundary and clock contract."""

import math
import unittest

from runtime.charge.evidence.adopted_mix_finish_hold_decision import (
    adopted_mix_finish_hold_complete,
)
from runtime.safety.runtime_guard import RuntimeSafetyError
from rd_live_adoption import MIX_FINISH_HOLD_S


class AdoptedMixFinishHoldDecisionTests(unittest.TestCase):
    def test_below_exact_and_above_threshold(self):
        self.assertFalse(adopted_mix_finish_hold_complete(10.0, 10.0 + MIX_FINISH_HOLD_S - 0.01, MIX_FINISH_HOLD_S))
        self.assertTrue(adopted_mix_finish_hold_complete(10.0, 10.0 + MIX_FINISH_HOLD_S, MIX_FINISH_HOLD_S))
        self.assertTrue(adopted_mix_finish_hold_complete(10.0, 10.0 + MIX_FINISH_HOLD_S + 0.01, MIX_FINISH_HOLD_S))

    def test_nonfinite_elapsed_and_backward_clock_keep_exact_error(self):
        for anchor, now in (
            (2.0, 1.0),
            (math.nan, 2.0),
            (2.0, math.inf),
            (2.0, -math.inf),
            (math.inf, math.inf),
        ):
            with self.subTest(anchor=anchor, now=now):
                with self.assertRaisesRegex(
                    RuntimeSafetyError,
                    "^MIX_ADOPTED finish-hold monotonic clock moved backwards$",
                ):
                    adopted_mix_finish_hold_complete(anchor, now, MIX_FINISH_HOLD_S)


if __name__ == "__main__":
    unittest.main()
