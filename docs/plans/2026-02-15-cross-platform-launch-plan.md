# Cross-Platform Launch Scripts — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Provide double-click launch scripts for macOS and Windows so users never need to type terminal commands.

**Architecture:** Two self-contained native scripts (`run-tenordash.command` for macOS, `run-tenordash.bat` for Windows) at project root. Each handles Python detection, venv setup, dependency install, browser open, and server launch. No shared bootstrap.

**Tech Stack:** Bash (macOS), Batch (Windows), Flask on port 5001.

---

### Task 1: Create macOS launcher script

**Files:**
- Create: `run-tenordash.command`

**Step 1: Create the script**

```bash
#!/usr/bin/env bash
set -e

# cd to the directory where this script lives
cd "$(dirname "$0")"

echo "=== TenorDash ==="
echo ""

# Check for Python 3
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 is not installed."
    echo "Download it from https://www.python.org/downloads/"
    echo ""
    read -p "Press Enter to close..."
    exit 1
fi

# Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    echo "Setting up virtual environment..."
    python3 -m venv .venv
    source .venv/bin/activate
    echo "Installing dependencies..."
    pip install -r requirements.txt
    if [ $? -ne 0 ]; then
        echo ""
        echo "ERROR: Failed to install dependencies."
        read -p "Press Enter to close..."
        exit 1
    fi
else
    source .venv/bin/activate
fi

echo "Starting TenorDash at http://127.0.0.1:5001"
echo "Press Ctrl+C or close this window to stop."
echo ""

# Open browser
open http://127.0.0.1:5001 &

# Run server (foreground — keeps terminal open)
python3 app.py
```

**Step 2: Make it executable**

Run: `chmod +x run-tenordash.command`

**Step 3: Test manually**

Run: `./run-tenordash.command`
Expected: Venv activates (or creates), deps install if needed, browser opens, Flask starts on port 5001.
Stop with Ctrl+C.

**Step 4: Commit**

```bash
git add run-tenordash.command
git commit -m "Add macOS launcher script (#12)"
```

---

### Task 2: Create Windows launcher script

**Files:**
- Create: `run-tenordash.bat`

**Step 1: Create the script**

```batch
@echo off
setlocal

:: cd to the directory where this script lives
cd /d "%~dp0"

echo === TenorDash ===
echo.

:: Check for Python
where python >nul 2>nul
if errorlevel 1 (
    echo ERROR: Python is not installed.
    echo Download it from https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

:: Create virtual environment if it doesn't exist
if not exist ".venv" (
    echo Setting up virtual environment...
    python -m venv .venv
    call .venv\Scripts\activate.bat
    echo Installing dependencies...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo ERROR: Failed to install dependencies.
        pause
        exit /b 1
    )
) else (
    call .venv\Scripts\activate.bat
)

echo Starting TenorDash at http://127.0.0.1:5001
echo Press Ctrl+C or close this window to stop.
echo.

:: Open browser
start http://127.0.0.1:5001

:: Run server (foreground — keeps window open)
python app.py
```

**Step 2: Commit**

```bash
git add run-tenordash.bat
git commit -m "Add Windows launcher script (#12)"
```

---

### Task 3: Update README Getting Started section

**Files:**
- Modify: `README.md:25-34`

**Step 1: Replace the Getting Started section**

Replace lines 25-34 of `README.md` with:

```markdown
## Getting Started

### Quick Launch (recommended)

**macOS:** Double-click `run-tenordash.command` in Finder.

**Windows:** Double-click `run-tenordash.bat` in Explorer.

The script will set up a virtual environment, install dependencies, open your browser, and start the server. Close the terminal window or press `Ctrl+C` to stop.

### Manual Setup

```bash
python3 -m venv .venv
source .venv/bin/activate        # macOS/Linux
# .venv\Scripts\activate.bat     # Windows
pip install -r requirements.txt
python3 app.py
```

Open http://127.0.0.1:5001 in your browser.

The database (`fixed_advances.db`) is created automatically on first run.
```

**Step 2: Review the full README renders correctly**

Skim the file to confirm markdown is valid and section flow is clean.

**Step 3: Commit**

```bash
git add README.md
git commit -m "Update README with launcher instructions (#12)"
```

---

### Task 4: Smoke test the macOS launcher

**Step 1: Delete .venv to test fresh setup path**

```bash
rm -rf .venv
```

**Step 2: Run the launcher**

```bash
./run-tenordash.command
```

Expected:
- "Setting up virtual environment..." appears
- "Installing dependencies..." appears
- Browser opens to `http://127.0.0.1:5001`
- Dashboard loads

**Step 3: Stop and re-run to test existing-venv path**

Press Ctrl+C, then:
```bash
./run-tenordash.command
```

Expected: Skips venv creation, goes straight to "Starting TenorDash..."

**Step 4: Recreate .venv for normal use**

If tests destroyed venv, the re-run in Step 3 already recreated it. Verify `.venv/` exists.
