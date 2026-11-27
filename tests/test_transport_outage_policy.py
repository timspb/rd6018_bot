import unittest

from runtime.production_runtime import (
    _is_physical_transport_error,
    _is_recoverable_link_boundary_error,
)


class TransportOutagePolicyTests(unittest.TestCase):
    def test_policy_owner_is_the_transport_module(self):
        import runtime.physical.transports.error_policy as policy
        self.assertIs(_is_physical_transport_error, policy._is_physical_transport_error)
        self.assertIs(_is_recoverable_link_boundary_error, policy._is_recoverable_link_boundary_error)

    def test_aiohttp_connector_error_is_classified_without_string_matching(self):
        import aiohttp
        self.assertTrue(_is_physical_transport_error(aiohttp.ClientError("edge offline")))

    def test_bare_timeout_cannot_be_a_recoverable_session_outage(self):
        self.assertFalse(_is_recoverable_link_boundary_error(TimeoutError("safety readback timeout")))

    def test_edge_disconnect_is_transport_outage(self):
        self.assertTrue(
            _is_physical_transport_error(
                RuntimeError("Not connected to rd6018-controller @ 192.168.1.28!")
            )
        )

    def test_connection_reset_is_transport_outage(self):
        self.assertTrue(_is_physical_transport_error(ConnectionResetError("connection reset by peer")))

    def test_request_timeout_is_transport_outage(self):
        self.assertTrue(_is_physical_transport_error(RuntimeError("request timeout error")))

    def test_output_off_confirmation_is_not_transport_outage(self):
        self.assertFalse(
            _is_physical_transport_error(
                RuntimeError("OFF command accepted but switch state was not confirmed")
            )
        )

    def test_accepted_off_without_confirmation_preserves_session_for_recovery(self):
        self.assertTrue(
            _is_recoverable_link_boundary_error(
                RuntimeError("requested output shutdown: OFF command accepted but switch state was not confirmed")
            )
        )

    def test_unrelated_safety_failure_does_not_preserve_session(self):
        self.assertFalse(
            _is_recoverable_link_boundary_error(
                RuntimeError("temperature safety verification failed")
            )
        )

    def test_safety_timeout_is_not_transport_outage(self):
        self.assertFalse(_is_physical_transport_error(TimeoutError("verification timeout")))


if __name__ == "__main__":
    unittest.main()
