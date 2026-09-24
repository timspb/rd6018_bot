import unittest

from runtime.v2_runtime import _is_physical_transport_error


class TransportOutagePolicyTests(unittest.TestCase):
    def test_edge_disconnect_is_transport_outage(self):
        self.assertTrue(
            _is_physical_transport_error(
                RuntimeError("Not connected to rd6018-controller @ 192.168.1.28!")
            )
        )

    def test_connection_reset_is_transport_outage(self):
        self.assertTrue(_is_physical_transport_error(ConnectionResetError("connection reset by peer")))

    def test_output_off_confirmation_is_not_transport_outage(self):
        self.assertFalse(
            _is_physical_transport_error(
                RuntimeError("OFF command accepted but switch state was not confirmed")
            )
        )

    def test_safety_timeout_is_not_transport_outage(self):
        self.assertFalse(_is_physical_transport_error(TimeoutError("verification timeout")))


if __name__ == "__main__":
    unittest.main()
