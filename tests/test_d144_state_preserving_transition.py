import unittest
from tools.d144_state_preserving_transition import OwnerTransition, TransitionError

class D144Tests(unittest.TestCase):
    def test_contract(self):
        self.assertTrue(callable(OwnerTransition))
        self.assertTrue(issubclass(TransitionError, RuntimeError))
