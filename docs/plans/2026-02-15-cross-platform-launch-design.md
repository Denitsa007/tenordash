# Design: Cross-Platform Launch Scripts

**Issue:** #12 — Decide and implement cross-platform launch method
**Date:** 2026-02-15
**Approach:** Separate native scripts (no shared bootstrap)

## Overview

Two self-contained launcher scripts at project root that provide a double-click launch experience on macOS and Windows. Each script handles Python detection, virtual environment setup, dependency installation, and browser opening.

## Files

| File | Action |
|------|--------|
| `run-tenordash.command` | New — macOS launcher |
| `run-tenordash.bat` | New — Windows launcher |
| `README.md` | Edit — update Getting Started section |

## `run-tenordash.command` (macOS)

Bash script, executable (`chmod +x`), double-clickable from Finder.

1. `cd` to script's own directory (works regardless of where Finder launches it)
2. Check `python3` exists on PATH; clear error + download link if missing
3. If `.venv/` doesn't exist: create with `python3 -m venv .venv`, install `requirements.txt`
4. Activate `.venv`
5. Open `http://127.0.0.1:5001` via `open` (background)
6. Run `python3 app.py` in foreground (server stops when terminal closes or Ctrl+C)

## `run-tenordash.bat` (Windows)

Batch script, double-clickable from Explorer. Same flow, Windows equivalents:

- `python` instead of `python3`
- `.venv\Scripts\activate.bat` instead of `source .venv/bin/activate`
- `start http://127.0.0.1:5001` instead of `open`
- `where python` instead of `which python3`

## Error Handling

- **Python not found:** Print message with `python.org/downloads` link, pause so window stays open
- **pip install fails:** Print error, do not proceed to launch
- **Port in use:** Flask's own error message is sufficient

## README Update

Replace current "Getting Started" with platform-specific double-click instructions. Keep manual `pip install && python3 app.py` as a "Manual Setup" fallback.

## Decisions

- **No startup delay before browser open** — Flask starts fast enough; can add a delay later if needed
- **No shared Python bootstrap** — each script is fully self-contained; duplication is minimal (~30 lines each)
- **Auto-setup venv** — scripts create `.venv` and install deps if missing, for true double-click experience
