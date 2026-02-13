import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "fixed_advances.db")
EXPORT_PATH = os.path.join(BASE_DIR, "export")

# Business rules
BASE_CURRENCY = "CHF"  # home currency — always rate 1.0
CONTINUATION_DAYS = 3  # business days before end date
INTEREST_YEAR_BASIS = 360  # day-count convention
CONTINUATION_ALERT_DAYS = 7  # dashboard alert window
