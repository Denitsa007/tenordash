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
