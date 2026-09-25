import unittest

from runtime.physical.lease import BenchLeaseProvider, BenchLeaseScope, BenchLeaseStatus


class BenchPhysicalLeaseTests(unittest.TestCase):
    def test_valid_disable_scope_is_accepted_and_audited(self):
        provider = BenchLeaseProvider(duration_s=60, clock=lambda: 100.0)
        lease = provider.request("operator", BenchLeaseScope.DISABLE_OUTPUT_ONLY)
        self.assertTrue(provider.validate(lease))
        self.assertEqual(provider.audit.records[-1].result, "ACCEPTED")

    def test_expired_lease_is_rejected(self):
        now = [100.0]
        provider = BenchLeaseProvider(duration_s=10, clock=lambda: now[0])
        lease = provider.request("operator", BenchLeaseScope.DISABLE_OUTPUT_ONLY)
        now[0] = 110.0
        self.assertFalse(provider.validate(lease))
        self.assertEqual(lease.status, BenchLeaseStatus.EXPIRED)

    def test_missing_lease_is_rejected(self):
        provider = BenchLeaseProvider(clock=lambda: 100.0)
        self.assertFalse(provider.validate(None))

    def test_revoked_lease_is_rejected(self):
        provider = BenchLeaseProvider(clock=lambda: 100.0)
        lease = provider.request("operator", BenchLeaseScope.DISABLE_OUTPUT_ONLY)
        provider.revoke(lease)
        self.assertFalse(provider.validate(lease))
