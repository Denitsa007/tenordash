# Excel Import — Design Document

**Date:** 2026-02-15
**Issues:** #5 (Import credit lines & fixed advances), #6 (Import bank list)
**Status:** Approved

## Purpose

One-time initial setup import. User uploads their existing Excel file (`.xlsx`/`.xlsm`) to seed the database with banks, credit lines, and fixed advances.

## Decisions

| Aspect | Decision |
|---|---|
| **Scope** | One-time initial setup import |
| **UI** | Single `/import` page with sidebar nav |
| **File format** | Excel only (`.xlsx`/`.xlsm`) |
| **Flow** | Upload → preview with validation → append/overwrite choice → confirm → results |
| **Parsing** | Shared `import_utils.py`, headers at row 4, column name mapping |
| **Bank extraction** | Derived from Credit Lines + Advances sheets (no separate Banks sheet) |
| **Validation** | Required fields, date/number parsing, FK consistency, per-row errors |
| **DB operations** | Single transaction, FK-order insert, rollback on failure |

## Import Flow

1. User navigates to `/import` (sidebar link)
2. Uploads Excel file (`.xlsx`/`.xlsm`)
3. App parses recognized sheets (`Credit Lines`, `Fixed Advances`)
4. Extracts banks from `BankKey` column in Credit Lines + `Bank` column in Advances
5. Shows preview — three collapsible sections (Banks, Credit Lines, Advances) with row counts, sample data, validation errors
6. If existing data detected: user chooses **Append** or **Overwrite**
7. User confirms → bulk insert in FK order: Banks → Credit Lines → Advances
8. Results summary: added/skipped/errors per entity

## Excel Format

Both sample files share the same structure:
- Row 1: title, rows 2-3: empty, **row 4: headers**, row 5+: data

### Credit Lines sheet columns
`Credit Line ID | BankKey | Description | Currency | Amount | Committed | Start Date | End Date | Note`

### Fixed Advances sheet columns
`ID | Bank | Linked Credit Line | Start Date | End Date | Continuation Date | Currency | Amount Original | Interest Amount | Description | Days | Interest Rate p.a. calc. | Is Currently Active`

### Skipped columns (calculated, not imported)
`Days`, `Interest Rate p.a. calc.`, `Is Currently Active`, `Description`

### Bank extraction
- `BankKey` values from Credit Lines sheet → `banks.bank_key`
- Matching `Bank` names from Advances sheet → `banks.bank_name`

## Validation Rules

- Required fields present and non-empty (id, dates, currency, amount)
- Dates parseable (ISO or Excel date format)
- Amounts numeric
- FK references valid (advance credit_line_id exists in parsed credit lines)
- Rows with errors flagged but don't block the rest

## New Files

- `import_utils.py` — Excel parsing, column mapping, validation
- `templates/import.html` — Import page template

## Modified Files

- `app.py` — routes: `GET /import`, `POST /api/import/preview`, `POST /api/import/execute`
- `db.py` — `bulk_insert_banks()`, `bulk_insert_credit_lines()`, `bulk_insert_advances()`, `clear_all_data()`
- `templates/base.html` — sidebar nav item
- `static/style.css` — import page styles
- `static/app.js` — import form handlers

## Database Operations

- **Insert order:** Banks → Credit Lines → Advances (FK dependencies)
- **Overwrite mode:** Delete in reverse FK order (advances → credit lines → banks), then insert
- **Single transaction** with rollback on failure
- Banks use `INSERT OR IGNORE` (idempotent by bank_key)
