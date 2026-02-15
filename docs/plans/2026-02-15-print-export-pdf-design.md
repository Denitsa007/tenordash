# Design: Print / Export PDF

**Issue:** #7 — Add Print / Export PDF for dashboard and list views
**Date:** 2026-02-15
**Approach:** Pure `@media print` CSS + `window.print()` button (no dependencies)

## Overview

Add a Print button to each page that triggers `window.print()`. A print-optimized `@media print` stylesheet hides navigation chrome and reformats tables for paper. Users can "Save as PDF" from the browser print dialog. ECB FX rates appear as a footer on printed output.

## Files

| File | Action |
|------|--------|
| `static/style.css` | Add `@media print` block |
| `templates/base.html` | Add print button in topbar, add print-only FX footer |

No backend changes, no new dependencies.

## Print Button

A "Print" button added to `.topbar-actions` on all four pages (dashboard, advances, credit_lines, banks) via `base.html`. Calls `window.print()`. Hidden in print output itself.

## `@media print` CSS

### Page orientation

```css
@page { size: landscape; }
```

Landscape by default — user can override in print dialog.

### Elements hidden

- `.sidebar` — entire nav sidebar
- `.topbar-actions` — all action buttons (including print button)
- `.row-actions` — edit/delete buttons in table rows
- `.sort-indicator` — column sort arrows
- `.filter-pills` — currency/status filters
- `.modal-overlay` — any open modals
- `.panel` — slide-out panels

### Layout adjustments

- `.main` → `margin-left: 0`, full page width
- `.dashboard-grid` → `grid-template-columns: 1fr` (stack vertically: instruments table, then continuations + utilization)
- Tables → reduced font size (~10px), reduced cell padding, `width: 100%`
- Monospace columns → slightly compressed

### FX rates print footer

The FX rates currently live inside `.sidebar` (which is hidden for print). A duplicate print-only block is added to `base.html` outside the sidebar:
- `display: none` in normal view
- `display: block` in `@media print`
- Uses the same Jinja template variables (`fx_rates`, `currencies`, `BASE_CURRENCY`, `ecb_date`) — no backend changes

## Decisions

- **Landscape default** — via `@page { size: landscape }`, user can still override in print dialog
- **Dashboard right sidebar included** — continuations and utilization bars print below the main table (stacked layout)
- **FX rates in print footer** — duplicated as a print-only block to avoid complex CSS repositioning
- **No server-side PDF** — browser print + Save as PDF covers the use case with zero dependencies
- **No forced page breaks** — let browser handle pagination naturally
