"""Genesis TEST Admin Global ID allowlist checks."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from demo_backend.config import DemoConfigurationError, read_repo_test_admin_ids


class TestOwnerAdminEnvFile(unittest.TestCase):
    def test_tracked_owner_allowlist_contains_requested_global_id(self):
        ids = read_repo_test_admin_ids()
        self.assertIn("0000003101", ids)
        self.assertIn("0000003257", ids)
        self.assertIn("0000003021", ids)

    def test_owner_can_change_single_env_line(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / ".env.admin-global-ids"
            p.write_text("EFHC_TEST_ADMIN_GLOBAL_IDS=0000003101,0000003021\n", encoding="utf-8")
            self.assertEqual(read_repo_test_admin_ids(p), frozenset({"0000003101", "0000003021"}))
            p.write_text("EFHC_TEST_ADMIN_GLOBAL_IDS=0000003101\n", encoding="utf-8")
            self.assertEqual(read_repo_test_admin_ids(p), frozenset({"0000003101"}))

    def test_bad_or_duplicate_entries_fail_closed(self):
        bad_values = (
            "EFHC_TEST_ADMIN_GLOBAL_IDS=3101\n",
            "EFHC_TEST_ADMIN_GLOBAL_IDS=0000003101,0000003101\n",
            "ADMIN_GLOBAL_IDS=0000003101\n",
            "EFHC_TEST_ADMIN_GLOBAL_IDS=0000003101\nEFHC_TEST_ADMIN_GLOBAL_IDS=0000003021\n",
            "EFHC_TEST_ADMIN_GLOBAL_IDS=0000003101,\n",
        )
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / ".env.admin-global-ids"
            for raw in bad_values:
                with self.subTest(raw=raw):
                    p.write_text(raw, encoding="utf-8")
                    with self.assertRaises(DemoConfigurationError):
                        read_repo_test_admin_ids(p)


if __name__ == "__main__":
    unittest.main()
