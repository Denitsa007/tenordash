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
