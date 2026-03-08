import os
import tempfile
import unittest
from datetime import date
from unittest import mock

import db
import seed


class SeedTests(unittest.TestCase):
    def setUp(self):
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        db_path = os.path.join(tmpdir.name, "test_seed.db")

        orig_db_path = db.DB_PATH
        self.addCleanup(setattr, db, "DB_PATH", orig_db_path)
        db.DB_PATH = db_path
        db.init_db()

    def test_seed_falls_back_when_excel_missing(self):
        with mock.patch("seed._load_excel_seed_data", return_value=None):
            seeded = seed.seed_if_empty()

        self.assertTrue(seeded)
        with db.get_db() as conn:
            bank_count = conn.execute("SELECT COUNT(*) FROM banks").fetchone()[0]
            cl_count = conn.execute("SELECT COUNT(*) FROM credit_lines").fetchone()[0]
            adv_count = conn.execute("SELECT COUNT(*) FROM fixed_advances").fetchone()[0]
            active_count = conn.execute(
                "SELECT COUNT(*) FROM fixed_advances WHERE start_date <= date('now') AND end_date > date('now')"
            ).fetchone()[0]

        self.assertGreater(bank_count, 0)
        self.assertGreater(cl_count, 0)
        self.assertGreater(adv_count, 0)
        self.assertGreater(active_count, 0)

        seeded_again = seed.seed_if_empty()
        self.assertFalse(seeded_again)

    def test_seed_refreshes_stale_excel_dates(self):
        stale_data = {
            "banks": {"rows": [{"bank_key": "B900", "bank_name": "Bank 900"}]},
            "credit_lines": {
                "rows": [{
                    "id": "CL900",
                    "bank_key": "B900",
                    "description": "Stale CL",
                    "currency": "CHF",
                    "amount": 10_000_000,
                    "committed": "Yes",
                    "start_date": "2025-01-01",
                    "end_date": "2025-03-01",
                    "note": None,
                }]
            },
            "advances": {
                "rows": [{
                    "id": "FV9001",
                    "bank": "Bank 900",
                    "credit_line_id": "CL900",
                    "start_date": "2025-01-10",
                    "end_date": "2025-02-10",
                    "continuation_date": "2025-02-05",
                    "currency": "CHF",
                    "amount_original": 1_000_000,
                    "interest_amount": 1_000.0,
                }]
            },
        }

        with mock.patch("seed._load_excel_seed_data", return_value=stale_data):
            seeded = seed.seed_if_empty()

        self.assertTrue(seeded)
        with db.get_db() as conn:
            row = conn.execute(
                "SELECT start_date, end_date, continuation_date FROM fixed_advances WHERE id = ?",
                ("FV9001",),
            ).fetchone()
            self.assertIsNotNone(row)
            end_date = date.fromisoformat(row["end_date"])
            self.assertGreater(end_date, date.today())


if __name__ == "__main__":
    unittest.main()
