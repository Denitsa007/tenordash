# Excel Import Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a single `/import` page where users upload an Excel file to seed banks, credit lines, and fixed advances.

**Architecture:** New `import_utils.py` module handles parsing and validation. Two new API routes handle preview and execute. New `import.html` template with vanilla JS. Bulk insert helpers added to `db.py`.

**Tech Stack:** Flask, SQLite3, openpyxl (already in requirements.txt), vanilla JS

---

### Task 1: Add bulk DB functions to `db.py`

**Files:**
- Modify: `db.py` (append after line 513, before EOF)
- Test: `tests/test_import.py` (create)

**Step 1: Write failing tests for bulk DB operations**

Create `tests/test_import.py`:

```python
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
```

**Step 2: Run tests to verify they fail**

Run: `cd "/Users/denitsa/Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian Vault/TenorDash" && python -m pytest tests/test_import.py -v`
Expected: FAIL — `AttributeError: module 'db' has no attribute 'bulk_insert_banks'`

**Step 3: Implement bulk DB functions**

Add to the end of `db.py`:

```python
# ── Bulk Import ──

def bulk_insert_banks(conn, rows):
    """Insert banks, skipping duplicates. Returns {added, skipped}."""
    added = 0
    skipped = 0
    for row in rows:
        existing = conn.execute(
            "SELECT bank_key FROM banks WHERE bank_key = ?", (row["bank_key"],)
        ).fetchone()
        if existing:
            skipped += 1
        else:
            conn.execute(
                "INSERT INTO banks (bank_key, bank_name) VALUES (?, ?)",
                (row["bank_key"], row["bank_name"]),
            )
            added += 1
    conn.commit()
    return {"added": added, "skipped": skipped}


def bulk_insert_credit_lines(conn, rows):
    """Insert credit lines. Returns {added, errors}."""
    added = 0
    errors = 0
    for row in rows:
        try:
            conn.execute(
                "INSERT INTO credit_lines (id, bank_key, description, currency, amount, "
                "committed, start_date, end_date, note, archived) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)",
                (row["id"], row["bank_key"], row.get("description"),
                 row["currency"], row["amount"], row["committed"],
                 row["start_date"], row.get("end_date"), row.get("note")),
            )
            added += 1
        except Exception:
            errors += 1
    conn.commit()
    return {"added": added, "errors": errors}


def bulk_insert_advances(conn, rows):
    """Insert fixed advances. Returns {added, errors}."""
    added = 0
    errors = 0
    for row in rows:
        try:
            conn.execute(
                "INSERT INTO fixed_advances (id, bank, credit_line_id, start_date, end_date, "
                "continuation_date, currency, amount_original, interest_amount) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (row["id"], row["bank"], row["credit_line_id"],
                 row["start_date"], row["end_date"], row["continuation_date"],
                 row["currency"], row["amount_original"], row["interest_amount"]),
            )
            added += 1
        except Exception:
            errors += 1
    conn.commit()
    return {"added": added, "errors": errors}


def clear_all_data(conn):
    """Delete all advances, credit lines, and banks (FK order)."""
    conn.execute("DELETE FROM fixed_advances")
    conn.execute("DELETE FROM credit_lines")
    conn.execute("DELETE FROM banks")
    conn.commit()
```

**Step 4: Run tests to verify they pass**

Run: `cd "/Users/denitsa/Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian Vault/TenorDash" && python -m pytest tests/test_import.py -v`
Expected: All 5 tests PASS

**Step 5: Commit**

```bash
git add db.py tests/test_import.py
git commit -m "Add bulk import DB functions and tests (#5, #6)"
```

---

### Task 2: Create `import_utils.py` — Excel parser and validators

**Files:**
- Create: `import_utils.py`
- Modify: `tests/test_import.py` (add parser tests)

**Step 1: Write failing tests for parsing**

Append to `tests/test_import.py`:

```python
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
```

**Step 2: Run tests to verify they fail**

Run: `cd "/Users/denitsa/Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian Vault/TenorDash" && python -m pytest tests/test_import.py::ParseExcelTests -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'import_utils'`

**Step 3: Implement `import_utils.py`**

Create `import_utils.py`:

```python
from datetime import date, datetime

from openpyxl import load_workbook


# Column mappings: Excel header → DB field
CL_COLUMN_MAP = {
    "Credit Line ID": "id",
    "BankKey": "bank_key",
    "Description": "description",
    "Currency": "currency",
    "Amount": "amount",
    "Committed": "committed",
    "Start Date": "start_date",
    "End Date": "end_date",
    "Note": "note",
}

ADV_COLUMN_MAP = {
    "ID": "id",
    "Bank": "bank",
    "Linked Credit Line": "credit_line_id",
    "Start Date": "start_date",
    "End Date": "end_date",
    "Continuation Date": "continuation_date",
    "Currency": "currency",
    "Amount Original": "amount_original",
    "Interest Amount": "interest_amount",
}

CL_REQUIRED = {"id", "bank_key", "currency", "amount", "committed", "start_date"}
ADV_REQUIRED = {"id", "bank", "credit_line_id", "start_date", "end_date",
                "continuation_date", "currency", "amount_original", "interest_amount"}


def _normalize_date(value):
    """Convert Excel date or string to ISO format string."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    s = str(value).strip()
    if not s or s == "--":
        return None
    # Try ISO parse
    try:
        return date.fromisoformat(s).isoformat()
    except ValueError:
        return s  # leave as-is, will be caught by validation


def _normalize_amount(value):
    """Convert to numeric, handling None and string formats."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return value
    s = str(value).replace(",", "").strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _parse_sheet(ws, column_map, header_row=4):
    """Parse a worksheet using column_map to rename headers. Returns list of dicts."""
    headers_raw = [cell.value for cell in ws[header_row]]
    # Map Excel headers to DB field names
    col_indices = {}
    for idx, header in enumerate(headers_raw):
        if header and header.strip() in column_map:
            col_indices[idx] = column_map[header.strip()]

    rows = []
    for row in ws.iter_rows(min_row=header_row + 1, values_only=True):
        # Skip completely empty rows
        if all(v is None for v in row):
            continue
        record = {}
        for idx, field in col_indices.items():
            record[field] = row[idx] if idx < len(row) else None
        # Skip rows where ID is empty (padding rows)
        id_field = "id" if "id" in record else None
        if id_field and not record.get(id_field):
            continue
        rows.append(record)

    return rows


def _normalize_credit_line(row):
    """Normalize a credit line row's types."""
    row["start_date"] = _normalize_date(row.get("start_date"))
    row["end_date"] = _normalize_date(row.get("end_date"))
    row["amount"] = _normalize_amount(row.get("amount"))
    if row["amount"] is not None:
        row["amount"] = int(row["amount"])
    # Normalize committed to Yes/No
    committed = str(row.get("committed", "")).strip()
    row["committed"] = "Yes" if committed.lower() in ("yes", "y", "1", "true") else "No"
    # Strip string fields
    for f in ("id", "bank_key", "description", "currency", "note"):
        if row.get(f) is not None:
            row[f] = str(row[f]).strip()
    return row


def _normalize_advance(row):
    """Normalize an advance row's types."""
    for f in ("start_date", "end_date", "continuation_date"):
        row[f] = _normalize_date(row.get(f))
    row["amount_original"] = _normalize_amount(row.get("amount_original"))
    if row["amount_original"] is not None:
        row["amount_original"] = int(row["amount_original"])
    row["interest_amount"] = _normalize_amount(row.get("interest_amount"))
    if row["interest_amount"] is not None:
        row["interest_amount"] = float(row["interest_amount"])
    # Strip string fields
    for f in ("id", "bank", "credit_line_id", "currency"):
        if row.get(f) is not None:
            row[f] = str(row[f]).strip()
    return row


def _extract_banks(credit_lines, advances):
    """Extract unique banks from credit lines (bank_key) and advances (bank name)."""
    # Build bank_key → bank_name mapping
    # Credit lines have bank_key; advances have bank (display name)
    # Match by looking at which bank name appears with which credit_line_id
    bank_keys = {}
    for cl in credit_lines:
        bk = cl.get("bank_key")
        if bk:
            bank_keys.setdefault(bk, None)

    # Build credit_line_id → bank_key lookup
    cl_to_bk = {cl["id"]: cl["bank_key"] for cl in credit_lines if cl.get("id") and cl.get("bank_key")}

    # From advances, map bank names to bank_keys via credit_line_id
    for adv in advances:
        cl_id = adv.get("credit_line_id")
        bank_name = adv.get("bank")
        if cl_id and bank_name and cl_id in cl_to_bk:
            bk = cl_to_bk[cl_id]
            if bk in bank_keys and bank_keys[bk] is None:
                bank_keys[bk] = bank_name

    # Fill any remaining None names with bank_key as fallback
    rows = []
    for bk, name in bank_keys.items():
        rows.append({"bank_key": bk, "bank_name": name or bk})

    return rows


def validate_credit_line(row):
    """Validate a credit line row. Returns list of error strings."""
    errors = []
    for field in CL_REQUIRED:
        if not row.get(field):
            errors.append(f"Missing required field: {field}")
    if row.get("amount") is not None and not isinstance(row["amount"], (int, float)):
        errors.append("Amount must be numeric")
    if row.get("start_date"):
        try:
            date.fromisoformat(row["start_date"])
        except (ValueError, TypeError):
            errors.append(f"Invalid start_date: {row['start_date']}")
    return errors


def validate_advance(row):
    """Validate an advance row. Returns list of error strings."""
    errors = []
    for field in ADV_REQUIRED:
        if not row.get(field) and row.get(field) != 0:
            errors.append(f"Missing required field: {field}")
    if row.get("amount_original") is not None and not isinstance(row["amount_original"], (int, float)):
        errors.append("Amount must be numeric")
    if row.get("interest_amount") is not None and not isinstance(row["interest_amount"], (int, float)):
        errors.append("Interest amount must be numeric")
    # Date order check
    try:
        s = date.fromisoformat(row.get("start_date", ""))
        e = date.fromisoformat(row.get("end_date", ""))
        if e <= s:
            errors.append("end_date must be later than start_date")
    except (ValueError, TypeError):
        pass  # Already caught by required field check
    return errors


def parse_excel(filepath):
    """Parse an Excel file and return structured data for preview.

    Returns dict with keys: banks, credit_lines, advances.
    Each value is {"rows": [...], "errors": [{"row": N, "messages": [...]}]}.
    """
    wb = load_workbook(filepath, read_only=True, data_only=True)
    try:
        result = {
            "banks": {"rows": [], "errors": []},
            "credit_lines": {"rows": [], "errors": []},
            "advances": {"rows": [], "errors": []},
        }

        # Parse Credit Lines sheet
        cl_sheet_name = None
        for name in wb.sheetnames:
            if "credit" in name.lower() and "line" in name.lower():
                cl_sheet_name = name
                break
        if cl_sheet_name:
            raw_cls = _parse_sheet(wb[cl_sheet_name], CL_COLUMN_MAP)
            for i, row in enumerate(raw_cls):
                row = _normalize_credit_line(row)
                errors = validate_credit_line(row)
                if errors:
                    result["credit_lines"]["errors"].append({"row": i + 5, "messages": errors})
                else:
                    result["credit_lines"]["rows"].append(row)

        # Parse Fixed Advances sheet
        adv_sheet_name = None
        for name in wb.sheetnames:
            if "advance" in name.lower() or "fixed" in name.lower():
                adv_sheet_name = name
                break
        if adv_sheet_name:
            raw_advs = _parse_sheet(wb[adv_sheet_name], ADV_COLUMN_MAP)
            for i, row in enumerate(raw_advs):
                row = _normalize_advance(row)
                errors = validate_advance(row)
                if errors:
                    result["advances"]["errors"].append({"row": i + 5, "messages": errors})
                else:
                    result["advances"]["rows"].append(row)

        # Extract banks from both sheets
        result["banks"]["rows"] = _extract_banks(
            result["credit_lines"]["rows"],
            result["advances"]["rows"],
        )

        return result
    finally:
        wb.close()
```

**Step 4: Run tests to verify they pass**

Run: `cd "/Users/denitsa/Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian Vault/TenorDash" && python -m pytest tests/test_import.py -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add import_utils.py tests/test_import.py
git commit -m "Add Excel parser and validation module (#5, #6)"
```

---

### Task 3: Add API routes for import preview and execute

**Files:**
- Modify: `app.py` (add 3 routes)
- Modify: `tests/test_import.py` (add API tests)

**Step 1: Write failing tests for API routes**

Append to `tests/test_import.py`:

```python
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
        # First preview to get parsed data structure
        with open(self.sample_file, "rb") as f:
            res = self.client.post(
                "/api/import/preview",
                data={"file": (f, "test.xlsx")},
                content_type="multipart/form-data",
            )
        self.assertEqual(res.status_code, 200)

        # Execute import
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
```

**Step 2: Run tests to verify they fail**

Run: `cd "/Users/denitsa/Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian Vault/TenorDash" && python -m pytest tests/test_import.py::ImportApiTests -v`
Expected: FAIL — 404 on `/import` route

**Step 3: Add routes to `app.py`**

Add imports at the top of `app.py` (after existing imports):

```python
import import_utils
```

Add routes before `# ── Template Helpers ──` section:

```python
# ── Import ──

@app.route("/import")
def import_page():
    with db_conn() as conn:
        existing = {
            "banks": conn.execute("SELECT COUNT(*) FROM banks").fetchone()[0],
            "credit_lines": conn.execute("SELECT COUNT(*) FROM credit_lines").fetchone()[0],
            "advances": conn.execute("SELECT COUNT(*) FROM fixed_advances").fetchone()[0],
        }
        return render_template("import.html", existing=existing)


@app.route("/api/import/preview", methods=["POST"])
def import_preview():
    if "file" not in request.files:
        return jsonify({"ok": False, "error": "No file uploaded"}), 400
    f = request.files["file"]
    if not f.filename:
        return jsonify({"ok": False, "error": "No file selected"}), 400

    import tempfile
    tmp = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
    try:
        f.save(tmp.name)
        tmp.close()
        result = import_utils.parse_excel(tmp.name)
    except Exception as e:
        return jsonify({"ok": False, "error": f"Failed to parse file: {e}"}), 400
    finally:
        os.unlink(tmp.name)

    with db_conn() as conn:
        existing = {
            "banks": conn.execute("SELECT COUNT(*) FROM banks").fetchone()[0],
            "credit_lines": conn.execute("SELECT COUNT(*) FROM credit_lines").fetchone()[0],
            "advances": conn.execute("SELECT COUNT(*) FROM fixed_advances").fetchone()[0],
        }

    return jsonify({
        "ok": True,
        "banks": {
            "count": len(result["banks"]["rows"]),
            "rows": result["banks"]["rows"],
            "errors": result["banks"]["errors"],
        },
        "credit_lines": {
            "count": len(result["credit_lines"]["rows"]),
            "rows": result["credit_lines"]["rows"][:5],
            "errors": result["credit_lines"]["errors"],
        },
        "advances": {
            "count": len(result["advances"]["rows"]),
            "rows": result["advances"]["rows"][:5],
            "errors": result["advances"]["errors"],
        },
        "existing": existing,
    })


@app.route("/api/import/execute", methods=["POST"])
def import_execute():
    if "file" not in request.files:
        return jsonify({"ok": False, "error": "No file uploaded"}), 400
    f = request.files["file"]
    mode = request.form.get("mode", "append")

    import tempfile
    tmp = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
    try:
        f.save(tmp.name)
        tmp.close()
        result = import_utils.parse_excel(tmp.name)
    except Exception as e:
        return jsonify({"ok": False, "error": f"Failed to parse file: {e}"}), 400
    finally:
        os.unlink(tmp.name)

    with db_conn() as conn:
        try:
            if mode == "overwrite":
                db.clear_all_data(conn)

            banks_result = db.bulk_insert_banks(conn, result["banks"]["rows"])
            cl_result = db.bulk_insert_credit_lines(conn, result["credit_lines"]["rows"])
            adv_result = db.bulk_insert_advances(conn, result["advances"]["rows"])
        except Exception as e:
            return jsonify({"ok": False, "error": f"Import failed: {e}"}), 500

    _try_export()

    return jsonify({
        "ok": True,
        "banks": banks_result,
        "credit_lines": cl_result,
        "advances": adv_result,
    })
```

**Step 4: Run tests to verify they pass**

Run: `cd "/Users/denitsa/Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian Vault/TenorDash" && python -m pytest tests/test_import.py -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add app.py tests/test_import.py
git commit -m "Add import preview and execute API routes (#5, #6)"
```

---

### Task 4: Create `import.html` template

**Files:**
- Create: `templates/import.html`

**Step 1: Create the template**

Create `templates/import.html`:

```html
{% extends "base.html" %}
{% set active_page = "import" %}
{% block title %}Import — TenorDash{% endblock %}

{% block content %}
<div class="topbar">
  <h2>Import Data</h2>
</div>

<!-- Upload Section -->
<div class="section">
  <div class="section-header">
    <h3>Upload Excel File</h3>
  </div>
  <div style="padding: 24px 20px;">
    <p style="font-size: 13px; color: var(--text-muted); margin-bottom: 16px;">
      Upload your Excel file (.xlsx or .xlsm) containing <strong>Credit Lines</strong> and
      <strong>Fixed Advances</strong> sheets. Banks will be extracted automatically.
    </p>
    <form id="import-upload-form" style="display: flex; gap: 12px; align-items: end;">
      <div class="form-group" style="flex: 1; margin-bottom: 0;">
        <label>Excel File</label>
        <input type="file" id="import-file" accept=".xlsx,.xlsm"
               style="padding: 8px; border: 1px dashed var(--border-medium); border-radius: 4px; width: 100%;" />
      </div>
      <button type="submit" class="btn-primary" id="preview-btn">
        <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="6" cy="6" r="4"/><path d="M9 9l3.5 3.5"/>
        </svg>
        Preview
      </button>
    </form>
  </div>
</div>

<!-- Preview Section (hidden until file parsed) -->
<div id="preview-section" style="display: none;">

  <!-- Existing Data Warning -->
  <div id="existing-warning" class="alert-box" style="display: none;">
    <div class="alert-title">
      <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor"><path d="M8 1a7 7 0 100 14A7 7 0 008 1zm0 3a1 1 0 011 1v4a1 1 0 01-2 0V5a1 1 0 011-1zm0 8a1 1 0 110-2 1 1 0 010 2z"/></svg>
      Existing data detected
    </div>
    <p style="font-size: 12px; color: var(--berry-dark); margin-bottom: 12px;" id="existing-counts"></p>
    <div style="display: flex; gap: 16px;">
      <label style="font-size: 13px; display: flex; align-items: center; gap: 6px; cursor: pointer;">
        <input type="radio" name="import-mode" value="append" checked /> Append to existing data
      </label>
      <label style="font-size: 13px; display: flex; align-items: center; gap: 6px; cursor: pointer;">
        <input type="radio" name="import-mode" value="overwrite" /> Overwrite (replace all)
      </label>
    </div>
  </div>

  <!-- Banks Preview -->
  <div class="section" id="banks-preview">
    <div class="section-header">
      <h3>Banks <span class="badge" id="banks-count" style="margin-left: 8px;"></span></h3>
    </div>
    <div id="banks-table-container" style="padding: 0;"></div>
  </div>

  <!-- Credit Lines Preview -->
  <div class="section" id="cl-preview">
    <div class="section-header">
      <h3>Credit Lines <span class="badge" id="cl-count" style="margin-left: 8px;"></span></h3>
    </div>
    <div id="cl-table-container" style="padding: 0;"></div>
    <div id="cl-errors" style="padding: 12px 20px; display: none;"></div>
  </div>

  <!-- Advances Preview -->
  <div class="section" id="adv-preview">
    <div class="section-header">
      <h3>Fixed Advances <span class="badge" id="adv-count" style="margin-left: 8px;"></span></h3>
    </div>
    <div id="adv-table-container" style="padding: 0;"></div>
    <div id="adv-errors" style="padding: 12px 20px; display: none;"></div>
  </div>

  <!-- Confirm / Cancel -->
  <div style="display: flex; gap: 12px; margin-top: 20px;">
    <button class="btn-primary" id="confirm-btn" onclick="executeImport()">
      <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="2"><polyline points="2 7 5.5 10.5 12 4"/></svg>
      Confirm Import
    </button>
    <button class="btn-secondary" onclick="resetImport()">Cancel</button>
  </div>
</div>

<!-- Results Section (hidden until import done) -->
<div id="results-section" style="display: none;">
  <div class="section">
    <div class="section-header">
      <h3>Import Complete</h3>
    </div>
    <div style="padding: 20px;" id="results-body"></div>
  </div>
  <div style="margin-top: 16px;">
    <a href="/import" class="btn-secondary">Import Another File</a>
    <a href="/" class="btn-primary" style="margin-left: 8px;">Go to Dashboard</a>
  </div>
</div>

{% endblock %}

{% block scripts %}
<script>
let currentFile = null;

document.getElementById('import-upload-form').addEventListener('submit', async function(e) {
  e.preventDefault();
  const fileInput = document.getElementById('import-file');
  if (!fileInput.files.length) return;
  currentFile = fileInput.files[0];

  const btn = document.getElementById('preview-btn');
  btn.disabled = true;
  btn.textContent = 'Parsing...';

  const formData = new FormData();
  formData.append('file', currentFile);

  try {
    const res = await fetch('/api/import/preview', { method: 'POST', body: formData });
    const data = await res.json();
    if (!data.ok) {
      alert(data.error || 'Failed to parse file');
      btn.disabled = false;
      btn.innerHTML = '<svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="2"><circle cx="6" cy="6" r="4"/><path d="M9 9l3.5 3.5"/></svg> Preview';
      return;
    }
    showPreview(data);
  } catch (err) {
    alert('Upload failed: ' + err.message);
  }
  btn.disabled = false;
  btn.innerHTML = '<svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="2"><circle cx="6" cy="6" r="4"/><path d="M9 9l3.5 3.5"/></svg> Preview';
});

function showPreview(data) {
  document.getElementById('preview-section').style.display = 'block';

  // Existing data warning
  const ex = data.existing;
  const total = ex.banks + ex.credit_lines + ex.advances;
  const warningEl = document.getElementById('existing-warning');
  if (total > 0) {
    document.getElementById('existing-counts').textContent =
      `Database currently has ${ex.banks} banks, ${ex.credit_lines} credit lines, and ${ex.advances} advances.`;
    warningEl.style.display = 'block';
  } else {
    warningEl.style.display = 'none';
  }

  // Banks
  document.getElementById('banks-count').textContent = data.banks.count;
  renderTable('banks-table-container', data.banks.rows,
    ['bank_key', 'bank_name'], ['Bank Key', 'Bank Name']);

  // Credit Lines
  document.getElementById('cl-count').textContent = data.credit_lines.count;
  renderTable('cl-table-container', data.credit_lines.rows,
    ['id', 'bank_key', 'currency', 'amount', 'committed', 'start_date'],
    ['ID', 'Bank Key', 'Currency', 'Amount', 'Committed', 'Start Date']);
  renderErrors('cl-errors', data.credit_lines.errors);

  // Advances
  document.getElementById('adv-count').textContent = data.advances.count;
  renderTable('adv-table-container', data.advances.rows,
    ['id', 'bank', 'credit_line_id', 'currency', 'amount_original', 'start_date', 'end_date'],
    ['ID', 'Bank', 'Credit Line', 'Currency', 'Amount', 'Start', 'End']);
  renderErrors('adv-errors', data.advances.errors);
}

function renderTable(containerId, rows, fields, headers) {
  const container = document.getElementById(containerId);
  if (!rows.length) {
    container.innerHTML = '<p style="padding: 16px; color: var(--text-muted); font-size: 13px;">No data found</p>';
    return;
  }
  let html = '<table class="data-table"><thead><tr>';
  headers.forEach(h => { html += '<th>' + h + '</th>'; });
  html += '</tr></thead><tbody>';
  rows.forEach(row => {
    html += '<tr>';
    fields.forEach(f => {
      let val = row[f];
      if (typeof val === 'number' && val > 999) val = val.toLocaleString();
      html += '<td>' + (val != null ? val : '&mdash;') + '</td>';
    });
    html += '</tr>';
  });
  html += '</tbody></table>';
  container.innerHTML = html;
}

function renderErrors(containerId, errors) {
  const el = document.getElementById(containerId);
  if (!errors || !errors.length) { el.style.display = 'none'; return; }
  el.style.display = 'block';
  let html = '<div class="currency-msg warn" style="display:block">';
  html += '<strong>' + errors.length + ' row(s) with errors (skipped):</strong><br>';
  errors.forEach(e => {
    html += 'Row ' + e.row + ': ' + e.messages.join(', ') + '<br>';
  });
  html += '</div>';
  el.innerHTML = html;
}

async function executeImport() {
  if (!currentFile) return;
  const mode = document.querySelector('input[name="import-mode"]:checked')?.value || 'append';
  const btn = document.getElementById('confirm-btn');
  btn.disabled = true;
  btn.textContent = 'Importing...';

  const formData = new FormData();
  formData.append('file', currentFile);
  formData.append('mode', mode);

  try {
    const res = await fetch('/api/import/execute', { method: 'POST', body: formData });
    const data = await res.json();
    if (!data.ok) {
      alert(data.error || 'Import failed');
      btn.disabled = false;
      btn.textContent = 'Confirm Import';
      return;
    }
    showResults(data);
  } catch (err) {
    alert('Import failed: ' + err.message);
    btn.disabled = false;
    btn.textContent = 'Confirm Import';
  }
}

function showResults(data) {
  document.getElementById('preview-section').style.display = 'none';
  document.getElementById('results-section').style.display = 'block';

  const body = document.getElementById('results-body');
  let html = '<table class="data-table"><thead><tr><th>Entity</th><th>Added</th><th>Skipped / Errors</th></tr></thead><tbody>';
  html += '<tr><td>Banks</td><td>' + data.banks.added + '</td><td>' + (data.banks.skipped || 0) + ' skipped</td></tr>';
  html += '<tr><td>Credit Lines</td><td>' + data.credit_lines.added + '</td><td>' + (data.credit_lines.errors || 0) + ' errors</td></tr>';
  html += '<tr><td>Fixed Advances</td><td>' + data.advances.added + '</td><td>' + (data.advances.errors || 0) + ' errors</td></tr>';
  html += '</tbody></table>';
  body.innerHTML = html;
}

function resetImport() {
  document.getElementById('preview-section').style.display = 'none';
  document.getElementById('import-file').value = '';
  currentFile = null;
}
</script>
{% endblock %}
```

**Step 2: Run the import page test**

Run: `cd "/Users/denitsa/Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian Vault/TenorDash" && python -m pytest tests/test_import.py::ImportApiTests::test_import_page_loads -v`
Expected: PASS

**Step 3: Commit**

```bash
git add templates/import.html
git commit -m "Add import page template (#5, #6)"
```

---

### Task 5: Add sidebar nav link and import page styles

**Files:**
- Modify: `templates/base.html` (add nav item after Banks)
- Modify: `static/style.css` (minor — no new styles needed, existing classes cover it)

**Step 1: Add sidebar nav link**

In `templates/base.html`, after the Banks nav item (line 48), add:

```html
    <a href="/import" class="nav-item {{ 'active' if active_page == 'import' }}">
      <svg viewBox="0 0 16 16" fill="currentColor"><path d="M8 1v9m0 0L5 7m3 3l3-3M2 12v2h12v-2"/></svg>
      Import
    </a>
```

**Step 2: Run all tests to verify nothing broke**

Run: `cd "/Users/denitsa/Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian Vault/TenorDash" && python -m pytest tests/ -v`
Expected: All tests PASS

**Step 3: Commit**

```bash
git add templates/base.html
git commit -m "Add Import link to sidebar navigation (#5, #6)"
```

---

### Task 6: Run full test suite and verify end-to-end

**Step 1: Run full test suite**

Run: `cd "/Users/denitsa/Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian Vault/TenorDash" && python -m pytest tests/ -v`
Expected: All tests PASS

**Step 2: Manual smoke test (start app and test import)**

Run: `cd "/Users/denitsa/Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian Vault/TenorDash" && .venv/bin/python app.py`

Then manually:
1. Navigate to http://localhost:5001/import
2. Upload `Sample Data Synthetic.xlsx`
3. Verify preview shows banks, credit lines, advances
4. Confirm import
5. Verify data appears on dashboard

**Step 3: Final commit with any fixes from smoke testing**

```bash
git add -A
git commit -m "Polish import feature after smoke testing (#5, #6)"
```
