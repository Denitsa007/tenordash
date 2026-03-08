import os
from copy import deepcopy
from datetime import date, timedelta

import db
import helpers
import import_utils

_SEED_FILE = os.path.join(os.path.dirname(__file__), "Sample Data Synthetic.xlsx")


def _safe_iso_add_days(value, delta_days):
    if not value:
        return value
    try:
        d = date.fromisoformat(value)
    except (TypeError, ValueError):
        return value
    return (d + timedelta(days=delta_days)).isoformat()


def _fallback_seed_data(today=None):
    today = today or date.today()
    return {
        "banks": {
            "rows": [
                {"bank_key": "B001", "bank_name": "Bank A"},
                {"bank_key": "B002", "bank_name": "Bank B"},
                {"bank_key": "B003", "bank_name": "Bank C"},
            ]
        },
        "credit_lines": {
            "rows": [
                {
                    "id": "CL001",
                    "bank_key": "B001",
                    "description": "Syndicated Facility",
                    "currency": "CHF",
                    "amount": 600_000_000,
                    "committed": "Yes",
                    "start_date": (today - timedelta(days=120)).isoformat(),
                    "end_date": (today + timedelta(days=330)).isoformat(),
                    "note": "Demo committed facility",
                },
                {
                    "id": "CL002",
                    "bank_key": "B002",
                    "description": "EUR Money Market Line",
                    "currency": "EUR",
                    "amount": 450_000_000,
                    "committed": "Yes",
                    "start_date": (today - timedelta(days=90)).isoformat(),
                    "end_date": (today + timedelta(days=240)).isoformat(),
                    "note": "Demo EUR line",
                },
                {
                    "id": "CL003",
                    "bank_key": "B003",
                    "description": "USD Revolver",
                    "currency": "USD",
                    "amount": 300_000_000,
                    "committed": "No",
                    "start_date": (today - timedelta(days=60)).isoformat(),
                    "end_date": (today + timedelta(days=300)).isoformat(),
                    "note": "Demo uncommitted line",
                },
            ]
        },
        "advances": {
            "rows": [
                {
                    "id": "FV0001",
                    "bank": "Bank A",
                    "credit_line_id": "CL001",
                    "start_date": (today - timedelta(days=27)).isoformat(),
                    "end_date": (today + timedelta(days=4)).isoformat(),
                    "continuation_date": helpers.suggest_continuation_date((today + timedelta(days=4)).isoformat()),
                    "currency": "CHF",
                    "amount_original": 80_000_000,
                    "interest_amount": 127_555.56,
                },
                {
                    "id": "FV0002",
                    "bank": "Bank A",
                    "credit_line_id": "CL001",
                    "start_date": (today - timedelta(days=15)).isoformat(),
                    "end_date": (today + timedelta(days=16)).isoformat(),
                    "continuation_date": helpers.suggest_continuation_date((today + timedelta(days=16)).isoformat()),
                    "currency": "CHF",
                    "amount_original": 55_000_000,
                    "interest_amount": 78_145.83,
                },
                {
                    "id": "FV0003",
                    "bank": "Bank B",
                    "credit_line_id": "CL002",
                    "start_date": (today - timedelta(days=21)).isoformat(),
                    "end_date": (today + timedelta(days=6)).isoformat(),
                    "continuation_date": helpers.suggest_continuation_date((today + timedelta(days=6)).isoformat()),
                    "currency": "EUR",
                    "amount_original": 62_000_000,
                    "interest_amount": 97_650.00,
                },
                {
                    "id": "FV0004",
                    "bank": "Bank C",
                    "credit_line_id": "CL003",
                    "start_date": (today - timedelta(days=12)).isoformat(),
                    "end_date": (today + timedelta(days=10)).isoformat(),
                    "continuation_date": helpers.suggest_continuation_date((today + timedelta(days=10)).isoformat()),
                    "currency": "USD",
                    "amount_original": 45_000_000,
                    "interest_amount": 64_625.00,
                },
            ]
        },
    }


def _load_excel_seed_data():
    if not os.path.exists(_SEED_FILE):
        return None
    return import_utils.parse_excel(_SEED_FILE)


def _refresh_dates(seed_data, today=None):
    """Shift stale seed dates forward so the demo always has active rows."""
    today = today or date.today()
    data = deepcopy(seed_data)

    advances = data.get("advances", {}).get("rows", [])
    end_dates = []
    for adv in advances:
        try:
            end_dates.append(date.fromisoformat(adv["end_date"]))
        except (KeyError, TypeError, ValueError):
            continue

    if not end_dates:
        return data

    target_latest_end = today + timedelta(days=21)
    delta_days = (target_latest_end - max(end_dates)).days
    if delta_days <= 0:
        return data

    for cl in data.get("credit_lines", {}).get("rows", []):
        cl["start_date"] = _safe_iso_add_days(cl.get("start_date"), delta_days)
        cl["end_date"] = _safe_iso_add_days(cl.get("end_date"), delta_days)

    for adv in advances:
        adv["start_date"] = _safe_iso_add_days(adv.get("start_date"), delta_days)
        adv["end_date"] = _safe_iso_add_days(adv.get("end_date"), delta_days)
        adv["continuation_date"] = _safe_iso_add_days(adv.get("continuation_date"), delta_days)
        if not adv.get("continuation_date") and adv.get("end_date"):
            adv["continuation_date"] = helpers.suggest_continuation_date(adv["end_date"])

    return data


def seed_if_empty():
    """Populate demo data from the synthetic Excel file when the database is empty.

    Must be called after db.init_db().  The entire seed runs in a single
    transaction so a partial failure leaves the database unchanged.
    """
    conn = db.get_db()
    try:
        existing_banks = conn.execute("SELECT COUNT(*) FROM banks").fetchone()[0]
        if existing_banks > 0:
            return False

        data = _load_excel_seed_data() or _fallback_seed_data()
        data = _refresh_dates(data)

        banks_result = db.bulk_insert_banks(conn, data["banks"]["rows"])
        cl_result = db.bulk_insert_credit_lines(conn, data["credit_lines"]["rows"])
        adv_result = db.bulk_insert_advances(conn, data["advances"]["rows"])

        if cl_result["errors"] or adv_result["errors"]:
            raise RuntimeError(
                f"Seed insert failed: credit_lines errors={cl_result['errors']}, "
                f"advances errors={adv_result['errors']}"
            )
        if banks_result["added"] == 0 and cl_result["added"] == 0 and adv_result["added"] == 0:
            raise RuntimeError("Seed insert produced no records")

        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
