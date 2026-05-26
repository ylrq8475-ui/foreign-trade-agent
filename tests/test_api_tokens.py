from __future__ import annotations

import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

from database.repository import CustomerRepository


class ApiTokenRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        tests_dir = Path(__file__).resolve().parent
        self.temp_dir = Path(tempfile.mkdtemp(prefix="api-token-", dir=str(tests_dir)))
        self.db_path = self.temp_dir / "workspace.sqlite3"
        self.repository = CustomerRepository(
            self.db_path,
            journal_mode="wal",
            synchronous="normal",
        )
        try:
            self.repository.init_db()
        except sqlite3.Error as exc:
            self.skipTest(f"SQLite write is unavailable in this environment: {exc}")

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_create_authenticate_and_revoke_token(self) -> None:
        token = self.repository.create_api_token(
            token_name="partner-a",
            scopes=["leads:search", "customers:import", "leads:search"],
            note="smoke",
        )

        self.assertTrue(token["plain_token"].startswith("cwa_"))
        self.assertEqual(
            ["leads:search", "customers:import"],
            token["scopes"],
        )

        authenticated = self.repository.authenticate_api_token(token["plain_token"])
        self.assertIsNotNone(authenticated)
        assert authenticated is not None
        self.assertEqual("partner-a", authenticated["token_name"])
        self.assertEqual("active", authenticated["status"])
        self.assertTrue(authenticated["last_used_at"])

        self.repository.revoke_api_token(token["id"])
        revoked = self.repository.authenticate_api_token(token["plain_token"])
        self.assertIsNone(revoked)

    def test_expired_token_does_not_authenticate(self) -> None:
        token = self.repository.create_api_token(
            token_name="expired",
            scopes=["leads:search"],
            expires_at="2000-01-01T00:00:00",
        )

        self.assertIsNone(self.repository.authenticate_api_token(token["plain_token"]))


if __name__ == "__main__":
    unittest.main()
