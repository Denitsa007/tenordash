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


import import_utils


class ParseExcelTests(unittest.TestCase):
    """Test parsing against the real sample file."""

    SAMPLE_FILE = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "Sample Data Synthetic.xlsx",
    )

    def test_parse_returns_three_entity_types(self):
        result = import_utils.parse_excel(self.SAMPLE_FILE)
        self.assertIn("banks", result)
        self.assertIn("credit_lines", result)
        self.assertIn("advances", result)

    def test_credit_lines_parsed(self):
        result = import_utils.parse_excel(self.SAMPLE_FILE)
        cl = result["credit_lines"]
        self.assertGreater(len(cl["rows"]), 0)
        first = cl["rows"][0]
        self.assertIn("id", first)
        self.assertIn("bank_key", first)
        self.assertIn("currency", first)
        self.assertIn("amount", first)

    def test_advances_parsed(self):
        result = import_utils.parse_excel(self.SAMPLE_FILE)
        adv = result["advances"]
        self.assertGreater(len(adv["rows"]), 0)
        first = adv["rows"][0]
        self.assertIn("id", first)
        self.assertIn("bank", first)
        self.assertIn("credit_line_id", first)
        self.assertIn("amount_original", first)

    def test_banks_extracted(self):
        result = import_utils.parse_excel(self.SAMPLE_FILE)
        banks = result["banks"]
        self.assertGreater(len(banks["rows"]), 0)
        first = banks["rows"][0]
        self.assertIn("bank_key", first)
        self.assertIn("bank_name", first)

    def test_dates_are_iso_strings(self):
        result = import_utils.parse_excel(self.SAMPLE_FILE)
        first_cl = result["credit_lines"]["rows"][0]
        # Should be ISO format like "2024-01-01"
        self.assertRegex(first_cl["start_date"], r"^\d{4}-\d{2}-\d{2}$")

    def test_amounts_are_numeric(self):
        result = import_utils.parse_excel(self.SAMPLE_FILE)
        first_cl = result["credit_lines"]["rows"][0]
        self.assertIsInstance(first_cl["amount"], (int, float))


class ValidationTests(unittest.TestCase):
    def test_validate_credit_line_missing_required_field(self):
        row = {"id": "CL001", "bank_key": "B001", "currency": "CHF"}
        errors = import_utils.validate_credit_line(row)
        self.assertTrue(len(errors) > 0)

    def test_validate_credit_line_valid(self):
        row = {"id": "CL001", "bank_key": "B001", "currency": "CHF",
               "amount": 100_000_000, "committed": "Yes", "start_date": "2026-01-01"}
        errors = import_utils.validate_credit_line(row)
        self.assertEqual(len(errors), 0)

    def test_validate_advance_missing_required_field(self):
        row = {"id": "FV0001", "bank": "Bank", "credit_line_id": "CL001"}
        errors = import_utils.validate_advance(row)
        self.assertTrue(len(errors) > 0)

    def test_validate_advance_valid(self):
        row = {"id": "FV0001", "bank": "Bank", "credit_line_id": "CL001",
               "start_date": "2026-01-10", "end_date": "2026-02-10",
               "continuation_date": "2026-02-05", "currency": "CHF",
               "amount_original": 50_000_000, "interest_amount": 125_000.0}
        errors = import_utils.validate_advance(row)
        self.assertEqual(len(errors), 0)

    def test_validate_advance_bad_date_order(self):
        row = {"id": "FV0001", "bank": "Bank", "credit_line_id": "CL001",
               "start_date": "2026-02-10", "end_date": "2026-01-10",
               "continuation_date": "2026-01-07", "currency": "CHF",
               "amount_original": 50_000_000, "interest_amount": 125_000.0}
        errors = import_utils.validate_advance(row)
        self.assertTrue(any("end_date" in e for e in errors))


import importlib.util

if importlib.util.find_spec("flask") is not None:
    import app as app_module
else:
    app_module = None


@unittest.skipUnless(app_module is not None, "flask not installed")
class ImportApiTests(unittest.TestCase):
    def setUp(self):
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        db_path = os.path.join(tmpdir.name, "test_import_api.db")
        self._orig_db_path = db.DB_PATH
        db.DB_PATH = db_path
        self.addCleanup(setattr, db, "DB_PATH", self._orig_db_path)
        db.init_db()

        app_module.app.config["TESTING"] = True
        app_module.app.config["PROPAGATE_EXCEPTIONS"] = False
        self.client = app_module.app.test_client()

        self.sample_file = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "Sample Data Synthetic.xlsx",
        )

    def test_import_page_loads(self):
        res = self.client.get("/import")
        self.assertEqual(res.status_code, 200)

    def test_preview_with_valid_file(self):
        with open(self.sample_file, "rb") as f:
            res = self.client.post(
                "/api/import/preview",
                data={"file": (f, "test.xlsx")},
                content_type="multipart/form-data",
            )
        self.assertEqual(res.status_code, 200)
        body = res.get_json()
        self.assertIn("banks", body)
        self.assertIn("credit_lines", body)
        self.assertIn("advances", body)
        self.assertGreater(body["advances"]["count"], 0)

    def test_preview_without_file_returns_400(self):
        res = self.client.post("/api/import/preview")
        self.assertEqual(res.status_code, 400)

    def test_execute_append_mode(self):
        with open(self.sample_file, "rb") as f:
            res = self.client.post(
                "/api/import/execute",
                data={"file": (f, "test.xlsx"), "mode": "append"},
                content_type="multipart/form-data",
            )
        self.assertEqual(res.status_code, 200)
        body = res.get_json()
        self.assertTrue(body["ok"])
        self.assertGreater(body["banks"]["added"], 0)
        self.assertGreater(body["credit_lines"]["added"], 0)
        self.assertGreater(body["advances"]["added"], 0)

    def test_execute_overwrite_mode(self):
        # Insert some existing data
        conn = db.get_db()
        try:
            conn.execute("INSERT INTO banks (bank_key, bank_name) VALUES (?, ?)", ("BXXX", "Old Bank"))
            conn.commit()
        finally:
            conn.close()

        with open(self.sample_file, "rb") as f:
            res = self.client.post(
                "/api/import/execute",
                data={"file": (f, "test.xlsx"), "mode": "overwrite"},
                content_type="multipart/form-data",
            )
        self.assertEqual(res.status_code, 200)
        body = res.get_json()
        self.assertTrue(body["ok"])

        # Old bank should be gone
        conn = db.get_db()
        try:
            old = conn.execute("SELECT * FROM banks WHERE bank_key = 'BXXX'").fetchone()
            self.assertIsNone(old)
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
