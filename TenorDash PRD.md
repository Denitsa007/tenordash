# TenorDash — Product Requirements Document

## 1. Overview

### Problem
Fixed advance borrowings are currently tracked in an Excel workbook (`Sample Data Fixed Advances.xlsm`). Each time a new advance is created, the user manually adds a row, entering bank, dates, currency, amount, and the interest amount received from the bank. Calculated fields (days, back-calculated interest rate, active status) are handled by Excel formulas. The workbook also contains legacy sheets (old dashboard, bank export, interest calculator) that add clutter and fragility.

### Goal
Replace the Excel workflow with a local desktop application that provides:
- Structured data entry for fixed advances and credit lines
- Automatic calculations (days, interest rate verification, active status)
- A dashboard of currently active instruments with continuation date reminders
- Data export for Power BI consumption

### Scope
This is a **single-user, local-only** treasury management tool. No authentication, no multi-user, no cloud sync.

---

## 2. Data Model

### 2.1 Credit Lines (`tblCreditLines`)

The reference/master table for borrowing facilities.

| Field          | Type      | Constraints                            | Notes                                     |
| -------------- | --------- | -------------------------------------- | ----------------------------------------- |
| Credit Line ID | text (PK) | Auto-generated (`CL001`, `CL002`, ...) | Sequential                                |
| Bank Key       | text      | Required                               | Internal bank identifier (e.g. `B003`)    |
| Description    | text      | Optional                               | Free text                                 |
| Currency       | text      | Required, references `currencies` table |                                           |
| Amount         | integer   | Required, > 0                          | Facility size (e.g. 510,000,000)          |
| Committed      | text      | Required, enum: `Yes`, `No`            | Whether facility is committed             |
| Start Date     | date      | Required                               |                                           |
| End Date       | date      | Optional (nullable)                    | Null = open-ended                         |
| Note           | text      | Optional                               | E.g. covenant ratios, cancellation status |

**Current volume:** 5 rows. Expected to stay small (< 20).

### 2.2 Fixed Advances (`tblFV`)

The main transaction table. One row per borrowing drawdown.

| Field              | Type      | Constraints                              | Notes                                      |
| ------------------ | --------- | ---------------------------------------- | ------------------------------------------ |
| ID                 | text (PK) | Auto-generated (`FV0001`, `FV0002`, ...) | Sequential                                 |
| Bank               | text      | Required                                 | Dropdown, validated against bank list      |
| Linked Credit Line | text (FK) | Required                                 | References `tblCreditLines.Credit Line ID` |
| Start Date         | date      | Required                                 |                                            |
| End Date           | date      | Required                                 | Maturity date                              |
| Continuation Date  | date      | Required                                 | Auto-suggested: 3 business days before End Date; editable |
| Currency           | text      | Required, references `currencies` table |                                            |
| Amount Original    | integer   | Required, > 0                            | Face value                                 |
| Interest Amount    | decimal   | Required, >= 0                           | Provided by bank                           |

**Calculated fields** (derived, not stored or auto-computed):

| Field | Formula | Purpose |
|-------|---------|---------|
| Days | `End Date - Start Date` | Tenor in days |
| Interest Rate p.a. (calc) | `Interest Amount / Amount Original * 360 / Days` | Back-calculated rate for verification |
| Description | `Currency + " " + Amount_in_m + " " + StartDate + " - " + EndDate` | Display label |
| Is Currently Active | `Today > Start Date AND Today <= End Date` | Active flag |

**Current volume:** 73 rows. Will grow by ~20-40 rows/year.

### 2.3 Relationships

```
tblCreditLines 1 ──── M tblFV
  (Credit Line ID)       (Linked Credit Line)
```

### 2.4 Banks (`tblBanks`)

Small reference table for bank dropdown values. Importable from Excel/CSV; editable in-app for occasional additions.

| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| Bank Key | text (PK) | Required | e.g. `B003` |
| Bank Name | text | Required | Display name for dropdowns |

**Current volume:** ~5 rows. Rarely changes.

### 2.5 Currencies (`currencies`)

Dynamic reference table for supported currencies. Ships with CHF, CZK, EUR, GBP, PLN, USD; new currencies can be added inline from any form.

| Field         | Type    | Constraints       | Notes                                    |
| ------------- | ------- | ----------------- | ---------------------------------------- |
| Code          | text (PK) | 3-letter ISO    | e.g. `CHF`, `CZK`, `PLN`                |
| CSS Color     | text    | Required, hex     | Auto-assigned from 12-color palette      |
| Display Order | integer | Required          | Controls dropdown/pill sort order        |
| ECB Available | integer | 0 or 1            | Whether ECB publishes rates for this code |

On creation, the app validates the code against the ECB Data API. Non-ECB currencies (e.g. exotic codes) are allowed but flagged with `ecb_available = 0`.

### 2.6 Reference Data

- **FX rates**: ECB cross rates fetched dynamically for all currencies with `ecb_available = 1`; converted to CHF per 1 unit of each currency; cached daily with automatic reset when currencies change.

---

## 3. Features

### 3.1 Credit Line Management

| Requirement | Detail |
|-------------|--------|
| Create | Input form for all fields; ID auto-generated |
| Edit | All fields editable after creation |
| List view | Table showing all credit lines with key fields |
| Delete / Archive | Soft delete or archive (credit lines may be referenced by advances) |

### 3.2 Fixed Advance Entry

| Requirement            | Detail                                                                            |
| ---------------------- | --------------------------------------------------------------------------------- |
| Create                 | Input form with dropdowns for Bank, Credit Line (choose one as default), Currency |
| Validation             | End Date > Start Date; Amount > 0; Interest Amount >= 0                           |
| Auto-calculate on save | Days, Interest Rate p.a., Description, Is Currently Active                        |
| List view              | Sortable/filterable table of all advances                                         |
| Edit                   | All input fields editable; recalculate derived fields on save                     |
| CL capacity warning    | On save, warns if the advance would exceed the linked credit line's facility; dismissable (user can save anyway) |
| Import                 | Import historical data from Excel (same format as sample file) with preview, validation, and append/overwrite modes; also import bank list from Excel/CSV |

### 3.3 Dashboard

| Requirement             | Detail                                                                                                                  |
| ----------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| Active instruments      | Filtered view: only rows where `Is Currently Active = true`                                                             |
| Summary cards           | Total active amount by currency (shown dynamically for all currencies with active instruments)                            |
| Continuation reminders  | Highlight advances with continuation date within next 7 days; list and calendar views with month navigation               |
| Credit line utilization | Amount drawn vs. facility size per credit line with progress bars; aggregate utilization card in CHF equivalent via ECB rates |
| ECB FX rates            | Displayed in the navigation sidebar on every page (via context processor); shows cross rates for all active currencies    |

### 3.4 Print / Export to PDF ✅

| Requirement | Detail | Status |
|-------------|--------|--------|
| Scope | Dashboard view and list views (advances, credit lines) should be printable or exportable as PDF | Implemented |
| Trigger | Button in the UI (e.g. "Print / Export PDF") | Implemented |
| Approach | Use the browser's native print functionality (`window.print()`) with a print-optimized CSS stylesheet | Implemented |
| Styling | Print stylesheet hides navigation, buttons, and non-essential chrome; formats tables to fit page width; landscape default; FX rates footer | Implemented |

### 3.5 Power BI Integration ✅

| Requirement | Detail | Status |
|-------------|--------|--------|
| Approach | Auto-export `.xlsx` on every advance/credit line save (no ODBC driver needed) | Implemented |
| Format | Excel (`.xlsx`) with sheet and column names matching the sample file (`tblFV`, `tblCreditLines`) | Implemented |
| Content | Export `tblFV` and `tblCreditLines` as clean, flat tables with calculated fields | Implemented |
| Location | Configurable export path via Settings modal with folder browser | Implemented |
| Power BI setup | Point Power BI data source at the export file; refreshes pick up latest data automatically | Ready |

### 3.6 Settings

| Requirement | Detail |
|-------------|--------|
| Display unit | Configurable amount display: full, thousands (K), or millions (M) |
| Continuation limit | Number of upcoming continuations to show (3, 5, 10, or all) |
| Export path | Folder where `.xlsx` exports are saved; includes folder browser for selection |
| Access | Settings modal accessible from navigation sidebar on every page |

---

## 4. Non-Functional Requirements

| Requirement          | Detail                                                          |
| -------------------- | --------------------------------------------------------------- |
| **Local only**       | All data stored on disk. Only external call: ECB API for FX rates. |
| **Single user**      | No auth, no concurrency concerns                                |
| **Data persistence** | SQLite database (or similar embedded store)                     |
| **Portable**         | Should run on Windows (primary) and macOS (secondary)           |
| **Data safety**      | Export/backup capability; no silent data loss                   |
| **Performance**      | Dataset is tiny (< 200 rows). Performance is not a concern.     |

---

## 5. Complexity Assessment

### Verdict: Low-to-Medium Complexity

This is a straightforward CRUD app with a simple relational model (4 tables, 1 relationship) and a small dataset.

| Dimension | Assessment |
|-----------|-----------|
| **Data model** | Simple — 4 tables (banks, currencies, credit_lines, fixed_advances), 1 foreign key, handful of calculated fields |
| **Business logic** | Minimal — date arithmetic, one interest rate formula, active flag |
| **UI** | Standard — 2 input forms, 2 list views, 1 dashboard with summary cards |
| **Integration** | Light — auto-export `.xlsx` for Power BI + ECB API for FX rates |
| **Scale** | Trivial — < 200 rows, single user |
| **Auth / security** | None — local only |

### What makes it easy
- Tiny dataset, no performance optimization needed
- No multi-user, no auth, no API
- Simple calculations (no complex financial modeling)
- Clear, well-structured existing data model to replicate

### What needs attention
- **Data migration**: Importing the 73 existing rows from Excel (one-time)
- **Continuation date reminders**: Need a mechanism to surface these on app open (not push notifications — just visual indicators)
- **Power BI compatibility**: Export format must match what the existing Power BI report expects (column names, data types)

---

## 6. Technology Options

Given "local only" and the complexity level, reasonable choices include:

| Option | Stack | Pros | Cons |
|--------|-------|------|------|
| **A. Python + Textual** | Python, Textual (TUI), SQLite | Fast to build, runs anywhere, no browser needed | Terminal UI may feel limited |
| **B. Python + web UI** | Python (Flask/FastAPI), HTML/JS, SQLite | Familiar web UI, easy dashboards | Requires running a local server |
| **C. Electron / Tauri** | TypeScript or Rust + web frontend | Native-feeling desktop app | Heavier build tooling |
| **D. Python + DearPyGui** | Python, DearPyGui, SQLite | True desktop GUI, no browser | Less common framework |

Recommendation depends on user preference for UI style and development speed vs. polish.

---

## 7. Migration Path

1. **Import bank list**: From Excel/CSV into `tblBanks`
2. **Import credit lines**: From sample Excel file (`tblCreditLines` sheet)
3. **Import historical advances**: From sample Excel file (`tblFV` sheet, 73 rows)
4. **Parallel run**: Keep Excel as backup during initial period
5. **Cutover**: Once confident, Excel becomes archive only
6. **Power BI reconnect**: Point Power BI data source from Excel to the app's auto-export file

---

## 8. Resolved Questions

- [x] **Bank list management** — Small reference table (`tblBanks`), importable from Excel/CSV, editable in-app for rare additions.
- [x] **Continuation date** — Auto-suggested as 3 business days before End Date; editable by user.
- [x] **Power BI column/sheet names** — Must match the sample Excel file exactly.
- [x] **FX conversion** — ECB Data API for dynamic cross rates via EUR (needed for credit line utilization in CHF equivalent). URL built dynamically from active currencies.
- [x] **Currencies** — Dynamic via `currencies` table. Ships with CHF, CZK, EUR, GBP, PLN, USD; new currencies added inline with ECB validation and auto-assigned colors.
- [x] **Strict advance date validation** — Server-side validation enforces `End Date > Start Date` for create/update.
- [x] **Power BI integration implementation** — Auto-export `.xlsx` on every save via `export.py` (openpyxl); export path configurable in Settings.
- [x] **Rolling calendar** — Not needed; removed from scope.
- [x] **Settings** — Display unit, continuation display limit, and export path configurable via Settings modal.
- [x] **Continuation calendar** — List and calendar views with month navigation for upcoming continuations.

## 9. App Launch / Packaging

Currently the app requires running `python app.py` from the terminal. Options for a simpler launch experience:

| Option | How it works | Pros | Cons |
|--------|-------------|------|------|
| **A. Launcher scripts (`.command` + `.bat`)** | Double-clickable launchers: macOS `.command` and Windows `.bat` that run the app and open the browser | Zero dependencies beyond Python; trivial to set up; works on both macOS and Windows | Terminal/console window stays open in background |
| **B. macOS Automator / Shortcut** | Automator app or Shortcuts action that runs the Flask server and opens `localhost` in browser | Feels like a native app launch; can add a custom icon | macOS-only; slightly more setup |
| **C. PyInstaller / py2app** | Bundle into a standalone `.app` (macOS) or `.exe` (Windows) with embedded Python | True double-click app; no Python install needed for end user | Larger file size; build step required; harder to update |
| **D. `launchd` / Login Item (macOS)** | Register as a background service that starts on login; user just opens browser to `localhost:5000` | Always running, instant access | Always consuming resources; overkill for occasional use |

**Recommendation:** Start with **Option A** (cross-platform launcher scripts: `.command` for macOS and `.bat` for Windows) for simplicity. If a more polished experience is needed later, upgrade to **Option C** (PyInstaller/py2app).

**Resolution:** Option A implemented — `run-tenordash.command` (macOS) and `run-tenordash.bat` (Windows) included in v1.0.0.

## 10. Phase 2 — Nice-to-Have

| Feature | Description | Priority |
|---------|-------------|----------|
| **Repayment scenario analysis** | Given active advances across multiple currencies, model which advance(s) to repay early to minimize combined interest cost and FX risk. Inputs: current ECB rates, remaining tenor, interest amounts. Output: ranked repayment options with projected savings. | Nice-to-have |

## 11. Open Questions

- [x] Preferred technology stack / UI style — **Flask web UI** chosen after reviewing mockups (terminal TUI, web UI, desktop app)
- [x] App launch method — **Option A** (cross-platform launcher scripts) implemented; see Section 9
- [x] Power BI auto-export implementation details and final export path UX — implemented with configurable export path + folder browser in Settings
