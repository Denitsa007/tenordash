# Fixed Advances App

A local Flask web app for tracking treasury fixed advance borrowings — replacing an Excel-based workflow with structured data entry, automatic calculations, and a dashboard with continuation date alerts.

## What It Does

- **Dashboard** — Active instruments at a glance, summary cards (CHF/EUR totals), upcoming continuation alerts, credit line utilization bars
- **Fixed Advances CRUD** — Create, edit, delete borrowing drawdowns with auto-generated IDs (`FV0001`, `FV0002`, ...) and live calculation preview (days, back-calculated interest rate)
- **Credit Lines** — Manage borrowing facilities with bank linkage, currency, committed status
- **Banks** — Simple reference table for bank dropdowns
- **Continuation Date Auto-Suggest** — 3 business days before maturity, editable
- **ECB Rate** — Fetches EUR/CHF from ECB API for credit line utilization in CHF equivalent

## Tech Stack

- **Python / Flask** — backend and routing
- **SQLite** — embedded database (created at runtime)
- **Vanilla JS** — slide-out panels, filters, live calculations
- **No ORM** — raw parameterized SQL, 3 tables, <200 rows

## Getting Started

```bash
pip install flask
python3 app.py
```

Open http://127.0.0.1:5001 in your browser.

The database (`fixed_advances.db`) is created automatically on first run.

## Project Structure

```
├── app.py              # Flask routes and template filters
├── db.py               # SQLite schema, queries
├── helpers.py          # Date math, interest rate calc, business-day logic
├── ecb.py              # ECB API client with daily cache
├── config.py           # Paths and business rule constants
├── static/
│   ├── style.css       # Full UI styling
│   ├── app.js          # Panel close handlers
│   └── logo.png        # Monogram
├── templates/
│   ├── base.html       # Sidebar layout shell
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

## Status

Phase 1 (core CRUD + dashboard) is complete. Phase 2 (Excel/CSV import, `.xlsx` auto-export for Power BI) is planned.

---

Created by [Denitsa Stachowski](https://denitsa.ch)
