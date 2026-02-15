import os
import tempfile
import unittest

import db


class BulkDbTests(unittest.TestCase):
    def setUp(self):
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        db_path = os.path.join(tmpdir.name, "test_import.db")
        self._orig_db_path = db.DB_PATH
        db.DB_PATH = db_path
        self.addCleanup(setattr, db, "DB_PATH", self._orig_db_path)
        db.init_db()

    def test_bulk_insert_banks(self):
        conn = db.get_db()
        try:
            rows = [
                {"bank_key": "B001", "bank_name": "Alpha Bank"},
                {"bank_key": "B002", "bank_name": "Beta Bank"},
            ]
            result = db.bulk_insert_banks(conn, rows)
            self.assertEqual(result["added"], 2)
            self.assertEqual(result["skipped"], 0)
            banks = db.get_banks(conn)
            self.assertEqual(len(banks), 2)
        finally:
            conn.close()

    def test_bulk_insert_banks_skips_duplicates(self):
        conn = db.get_db()
        try:
            db.upsert_bank(conn, "B001", "Existing Bank")
            rows = [
                {"bank_key": "B001", "bank_name": "Alpha Bank"},
                {"bank_key": "B002", "bank_name": "Beta Bank"},
            ]
            result = db.bulk_insert_banks(conn, rows)
            self.assertEqual(result["added"], 1)
            self.assertEqual(result["skipped"], 1)
        finally:
            conn.close()

    def test_bulk_insert_credit_lines(self):
        conn = db.get_db()
        try:
            conn.execute("INSERT INTO banks (bank_key, bank_name) VALUES (?, ?)", ("B001", "Bank"))
            conn.commit()
            rows = [
                {"id": "CL001", "bank_key": "B001", "description": "Facility A",
                 "currency": "CHF", "amount": 100_000_000, "committed": "Yes",
                 "start_date": "2026-01-01", "end_date": None, "note": None},
            ]
            result = db.bulk_insert_credit_lines(conn, rows)
            self.assertEqual(result["added"], 1)
            self.assertEqual(result["errors"], 0)
        finally:
            conn.close()

    def test_bulk_insert_advances(self):
        conn = db.get_db()
        try:
            conn.execute("INSERT INTO banks (bank_key, bank_name) VALUES (?, ?)", ("B001", "Bank"))
            conn.execute(
                "INSERT INTO credit_lines (id, bank_key, description, currency, amount, "
                "committed, start_date, end_date, note, archived) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                ("CL001", "B001", "Facility", "CHF", 100_000_000,
                 "Yes", "2026-01-01", None, None, 0),
            )
            conn.commit()
            rows = [
                {"id": "FV0001", "bank": "Bank", "credit_line_id": "CL001",
                 "start_date": "2026-01-10", "end_date": "2026-02-10",
                 "continuation_date": "2026-02-05", "currency": "CHF",
                 "amount_original": 50_000_000, "interest_amount": 125_000.0},
            ]
            result = db.bulk_insert_advances(conn, rows)
            self.assertEqual(result["added"], 1)
            self.assertEqual(result["errors"], 0)
        finally:
            conn.close()

    def test_clear_all_data(self):
        conn = db.get_db()
        try:
            conn.execute("INSERT INTO banks (bank_key, bank_name) VALUES (?, ?)", ("B001", "Bank"))
            conn.execute(
                "INSERT INTO credit_lines (id, bank_key, description, currency, amount, "
                "committed, start_date, end_date, note, archived) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                ("CL001", "B001", "Facility", "CHF", 100_000_000,
                 "Yes", "2026-01-01", None, None, 0),
            )
            conn.execute(
                "INSERT INTO fixed_advances (id, bank, credit_line_id, start_date, end_date, "
                "continuation_date, currency, amount_original, interest_amount) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                ("FV0001", "Bank", "CL001", "2026-01-10", "2026-02-10",
                 "2026-02-05", "CHF", 50_000_000, 125_000.0),
            )
            conn.commit()

            db.clear_all_data(conn)

            self.assertEqual(conn.execute("SELECT COUNT(*) FROM fixed_advances").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM credit_lines").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM banks").fetchone()[0], 0)
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
