"""Regression: temporary layout key never unlocks arbitrary Admin API."""
from __future__ import annotations

import unittest

from demo_backend.visual_admin_read import visual_admin_report_allowed


class VisualAdminReadPolicyTests(unittest.TestCase):
    def test_exact_aggregate_reports_read_only(self) -> None:
        for path in (
            "/api/admin/reports/overview",
            "/api/admin/reports/users",
            "/api/admin/reports/bank",
            "/api/admin/reports/panels",
            "/api/admin/reports/withdrawals",
            "/api/admin/reports/deposits",
            "/api/admin/bank/balance",
            "/api/admin/referrals/summary",
            "/api/admin/bonuses",
        ):
            self.assertTrue(visual_admin_report_allowed(path, "GET"), path)
            self.assertTrue(visual_admin_report_allowed(path, "HEAD"), path)
            for method in ("POST", "PATCH", "DELETE", "PUT"):
                self.assertFalse(visual_admin_report_allowed(path, method))

    def test_no_privileged_or_dynamic_admin_routes(self) -> None:
        for path in (
            "/api/admin", "/api/admin/access", "/api/admin/users/search",
            "/api/admin/users/0000000088",
            "/api/admin/withdrawals",
            "/api/admin/withdrawals/1/payout-reservation",
            "/api/admin/bank/mint", "/api/admin/bank/burn",
            "/api/admin/transfer",
            "/api/admin/ads/providers/secrets",
            "/api/admin/reports/overview/evil",
            "/api/admin/referrals/logs",
            "/api/admin/panels/123",
            "/api/admin/bonuses?global_id=1",
            "/api/admin/templates", "/api/staging/visual-access",
        ):
            self.assertFalse(visual_admin_report_allowed(path, "GET"), path)

    def test_unrecognized_or_case_mismatched_path_denied(self) -> None:
        self.assertFalse(
            visual_admin_report_allowed("/API/ADMIN/REPORTS/OVERVIEW", "GET")
        )
        self.assertFalse(
            visual_admin_report_allowed("/api/admin/reports/overview/", "GET")
        )


if __name__ == "__main__":
    unittest.main()
