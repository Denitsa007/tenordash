# Fixed Advances App — Product Requirements Document

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

| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| Credit Line ID | text (PK) | Auto-generated (`CL001`, `CL002`, ...) | Sequential |
| Bank Key | text | Required | Internal bank identifier (e.g. `B003`) |
| Description | text | Optional | Free text |
| Currency | text | Required, enum: `CHF`, `EUR` | |
| Amount | integer | Required, > 0 | Facility size (e.g. 510,000,000) |
| Committed | text | Required, enum: `Yes`, `No` | Whether facility is committed |
| Start Date | date | Required | |
| End Date | date | Optional (nullable) | Null = open-ended |
| Note | text | Optional | E.g. covenant ratios, cancellation status |

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
| Currency           | text      | Required, enum: `CHF`, `EUR`             |                                            |
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

### 2.5 Reference Data

- **Currency list**: `CHF`, `EUR` (hardcoded enum).
- **FX rates**: EUR/CHF rate fetched from ECB API for credit line utilization calculations.

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
| Import                 | Import historical data from Excel (same format as sample file); also import bank list from Excel/CSV |

### 3.3 Dashboard

| Requirement             | Detail                                                                                                                  |
| ----------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| Active instruments      | Filtered view: only rows where `Is Currently Active = true`                                                             |
| Summary cards           | Total active amount by currency (CHF, EUR)                                                                              |
| Continuation reminders  | Highlight advances with continuation date within next 7/14/30 days                                                      |
| Credit line utilization | Amount drawn vs. facility size per credit line (this will require FX translation - ECB API can be used to get the rate) |

### 3.4 Power BI Integration

| Requirement | Detail |
|-------------|--------|
| Approach | Auto-export `.xlsx` on every save (no ODBC driver or Python dependency needed) |
| Format | Excel (`.xlsx`) with sheet and column names matching the sample file (`tblFV`, `tblCreditLines`) |
| Content | Export `tblFV` and `tblCreditLines` as clean, flat tables |
| Location | Configurable export path |
| Power BI setup | Point Power BI data source at the export file; refreshes pick up latest data automatically |

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

This is a straightforward CRUD app with a simple relational model (2 tables, 1 relationship) and a small dataset.

| Dimension | Assessment |
|-----------|-----------|
| **Data model** | Simple — 2 tables, 1 foreign key, handful of calculated fields |
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
- [x] **FX conversion** — Use ECB API for EUR/CHF rates (needed for credit line utilization view).
- [x] **Currencies** — CHF and EUR only; hardcoded enum.
- [x] **Power BI integration** — Auto-export `.xlsx` on save (no ODBC/driver dependencies).
- [x] **Rolling calendar** — Not needed; removed from scope.

## 9. Open Questions

- [ ] Preferred technology stack / UI style — to be decided after reviewing UI examples
