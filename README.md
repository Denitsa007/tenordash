# Fixed Advances App

A local Flask web app for tracking treasury fixed advance borrowings — replacing an Excel-based workflow with structured data entry, automatic calculations, and a dashboard with continuation date alerts.

## What It Does

- **Dashboard** — Active instruments at a glance, summary cards per currency, upcoming continuation alerts, credit line utilization bars with aggregate CHF equivalent
- **Fixed Advances CRUD** — Create, edit, delete borrowing drawdowns with auto-generated IDs (`FV0001`, `FV0002`, ...), live calculation preview (days, back-calculated interest rate), and credit line capacity warnings
- **Credit Lines** — Manage borrowing facilities with bank linkage, currency, committed status
- **Banks** — Simple reference table for bank dropdowns
- **Dynamic Currency Management** — Add new currencies inline from any form via a "+" button; ECB validation, auto-assigned badge colors from a 12-color palette. Ships with CHF, CZK, EUR, GBP, PLN, USD; new currencies (e.g. JPY, SEK) can be added at any time
- **Continuation Date Auto-Suggest** — 3 business days before maturity, editable
- **ECB FX Rates** — Dynamically fetches cross rates from ECB Data API for all active currencies; cached daily with automatic cache reset when currencies change
- **Locale-Aware Formatting** — Amount fields use the browser's locale for thousands/decimal separators

## Tech Stack

- **Python / Flask** — backend and routing
- **SQLite** — embedded database (created at runtime)
- **Vanilla JS** — slide-out panels, filters, live calculations
- **No ORM** — raw parameterized SQL, 4 tables, <200 rows

## Getting Started

```bash
pip install flask
python3 app.py
```

Open http://127.0.0.1:5001 in your browser.

The database (`fixed_advances.db`) is created automatically on first run.

## Project Structure

```
├── app.py              # Flask routes, template filters, currency API
├── db.py               # SQLite schema, migrations, queries
├── helpers.py          # Date math, interest rate calc, business-day logic
├── ecb.py              # ECB Data API client (dynamic currencies, daily cache)
├── config.py           # Paths, business rules, base currency
├── static/
│   ├── style.css       # Full UI styling
│   ├── app.js          # Panel close handlers
│   └── logo.png        # Monogram
├── templates/
│   ├── base.html       # Sidebar layout, currency modal, dynamic CSS
│   ├── dashboard.html  # Summary cards, alerts, active instruments
│   ├── advances.html   # Advances list + slide-out form
│   ├── credit_lines.html
│   └── banks.html
└── Fixed Advances App PRD.md  # Product requirements
```

## Business Logic

- **Interest rate**: `interest_amount / amount_original × 360 / days` (360-day year convention)
- **Active flag**: `start_date <= today < end_date`
- **Continuation date**: 3 business days before end date (weekends only, no holiday calendar)
- **IDs**: Auto-incremented with prefix — `FV0001` for advances, `CL001` for credit lines
- **CL capacity check**: On save, compares current drawn amount + new advance against the credit line facility; warns if exceeded but allows the user to proceed
- **Currencies**: Stored in a `currencies` table with code, CSS color, display order, and ECB availability flag. New currencies are validated against the ECB API on creation; non-ECB currencies are allowed but flagged
- **FX conversion**: ECB cross rates via EUR — dynamically builds the API URL from active currencies, converts to CHF per 1 unit of each currency; cached daily with automatic reset on currency changes

## Status

Phase 1 (core CRUD + dashboard) is complete. Phase 2 (Excel/CSV import, `.xlsx` auto-export for Power BI) is planned.

---

Created by [Denitsa Stachowski](https://denitsa.ch)
