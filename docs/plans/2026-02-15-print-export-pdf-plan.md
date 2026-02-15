# Print / Export PDF — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add print-optimized output to all pages so users can print or "Save as PDF" via the browser.

**Architecture:** A `window.print()` button on each page, `@media print` CSS block to hide chrome and reformat tables, and a print-only FX rates footer block in the base template. Zero dependencies.

**Tech Stack:** CSS `@media print`, Jinja2 templates, vanilla JS (`window.print()`)

---

### Task 1: Add print button to all pages

**Files:**
- Modify: `templates/dashboard.html:10` (inside `.topbar-actions`)
- Modify: `templates/advances.html:9` (inside `.topbar-actions`)
- Modify: `templates/credit_lines.html:9` (inside `.topbar-actions`)
- Modify: `templates/banks.html:9` (inside `.topbar-actions`)

**Step 1: Add print button to each page**

Add this button as the **first child** inside each `<div class="topbar-actions">`:

```html
<button class="btn-secondary" onclick="window.print()">
  <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="2"><path d="M3.5 5V1.5h7V5"/><rect x="1.5" y="5" width="11" height="5.5" rx="1"/><path d="M3.5 8.5h7v4h-7z"/></svg>
  Print
</button>
```

This goes in all four files: `dashboard.html`, `advances.html`, `credit_lines.html`, `banks.html`.

**Step 2: Verify buttons appear**

Run: `python3 app.py` and check all four pages in browser.
Expected: A "Print" button appears in the top bar next to existing action buttons.

**Step 3: Commit**

```bash
git add templates/dashboard.html templates/advances.html templates/credit_lines.html templates/banks.html
git commit -m "Add Print button to all pages (#7)"
```

---

### Task 2: Add print-only FX rates footer to base template

**Files:**
- Modify: `templates/base.html:72` (after `</main>`, before the currency modal)

**Step 1: Add print-only FX footer**

Insert the following block at line 73 of `base.html`, between `</main>` (line 72) and the currency modal comment (line 74):

```html
  <!-- Print-only FX rates footer (hidden on screen, shown on print) -->
  {% if fx_rates is defined and fx_rates %}
  <div class="print-fx-footer">
    {% for curr in currencies %}
      {% if curr.code != BASE_CURRENCY and fx_rates.get(curr.code) %}
        <span>{{ curr.code }}/{{ BASE_CURRENCY }}: {{ "%.4f"|format(fx_rates[curr.code]) }}</span>
      {% endif %}
    {% endfor %}
    <span class="print-fx-source">Source: ECB {{ ecb_date or '' }}</span>
  </div>
  {% endif %}
```

This duplicates the FX data from the sidebar using the same Jinja variables. No backend changes.

**Step 2: Verify it's hidden on screen**

Run the app and confirm the FX footer is NOT visible in normal browser view (it won't be yet — we add `display: none` in the CSS task).

**Step 3: Commit**

```bash
git add templates/base.html
git commit -m "Add print-only FX rates footer block (#7)"
```

---

### Task 3: Add `@media print` CSS

**Files:**
- Modify: `static/style.css` (append at end of file, after line 1042)

**Step 1: Add the print stylesheet**

Append the following block to the end of `style.css`:

```css
/* ── Print Styles ── */

@media print {
  @page { size: landscape; }

  /* Hide navigation and interactive chrome */
  .sidebar,
  .topbar-actions,
  .row-actions,
  .sort-indicator,
  .filter-pills,
  .modal-overlay,
  .panel-overlay,
  .nav-badge,
  .cal-nav-btn,
  .continuation-view-switch { display: none !important; }

  /* Full-width layout (remove sidebar offset) */
  body { display: block; background: #fff; }
  .main {
    margin-left: 0;
    padding: 16px;
    min-height: auto;
  }

  /* Stack dashboard grid vertically */
  .dashboard-grid {
    grid-template-columns: 1fr;
  }

  /* Table adjustments */
  .data-table { font-size: 11px; }
  .data-table th { padding: 6px 10px; font-size: 10px; background: none; }
  .data-table td { padding: 8px 10px; }
  .mono { font-size: 11px; }

  /* Cards */
  .card { box-shadow: none; border: 1px solid #ddd; }
  .section { box-shadow: none; border: 1px solid #ddd; }

  /* Keep page title visible */
  .topbar { margin-bottom: 12px; }
  .topbar h2 { font-size: 18px; }

  /* Print-only FX footer */
  .print-fx-footer {
    display: flex !important;
    flex-wrap: wrap;
    gap: 8px 16px;
    padding: 12px 0;
    margin-top: 24px;
    border-top: 1px solid #ccc;
    font-size: 11px;
    color: #666;
  }
  .print-fx-source {
    width: 100%;
    font-size: 10px;
    color: #999;
    margin-top: 4px;
  }
}

/* Hide print FX footer on screen */
.print-fx-footer { display: none; }
```

**Key decisions in this CSS:**
- `@page { size: landscape }` — landscape default per user request
- `!important` on hide rules to override any inline styles
- Table font compressed from 13px → 11px, padding reduced, to fit landscape page
- Dashboard grid stacks to single column so continuations + utilization appear below instruments
- Cards and sections lose shadow, gain border for clean print rendering
- Calendar nav buttons and continuation view switch hidden (non-interactive in print)
- Print FX footer uses `display: flex !important` in print, `display: none` on screen

**Step 2: Verify print output**

Run the app. On each page, press `Cmd+P` (or click the Print button) and check the print preview:
- Sidebar hidden
- Action buttons hidden
- Table fits page width
- Row action buttons (edit/delete) hidden
- FX rates footer visible at bottom
- Dashboard: instruments table, then continuations + utilization stacked below

**Step 3: Commit**

```bash
git add static/style.css
git commit -m "Add @media print stylesheet with landscape default (#7)"
```

---

### Task 4: Visual smoke test all pages

**Step 1: Test dashboard print preview**

Open `http://127.0.0.1:5001/`, press `Cmd+P`.
Check:
- [ ] Sidebar hidden
- [ ] Print button hidden
- [ ] Summary cards visible
- [ ] Active instruments table visible, fits page
- [ ] Continuations widget visible below main content
- [ ] Utilization bars visible below continuations
- [ ] FX rates footer at bottom
- [ ] Landscape orientation

**Step 2: Test advances print preview**

Open `http://127.0.0.1:5001/advances`, press `Cmd+P`.
Check:
- [ ] Table columns fit page (12 cols in landscape)
- [ ] Edit/delete buttons hidden
- [ ] Sort arrows hidden
- [ ] Filter pills hidden
- [ ] FX rates footer at bottom

**Step 3: Test credit lines print preview**

Open `http://127.0.0.1:5001/credit-lines`, press `Cmd+P`.
Check:
- [ ] Table columns fit page (10 cols in landscape)
- [ ] Action buttons hidden
- [ ] FX rates footer at bottom

**Step 4: Test banks print preview**

Open `http://127.0.0.1:5001/banks`, press `Cmd+P`.
Check:
- [ ] Simple 3-column table renders cleanly
- [ ] FX rates footer at bottom

**Step 5: Fix any visual issues found**

If any element overflows, adjust padding or font-size in the `@media print` block.
