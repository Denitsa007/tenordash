from datetime import date, timedelta

import db
import helpers
from config import INTEREST_YEAR_BASIS


def _interest(amount, days, annual_rate):
    return round(amount * (annual_rate / 100.0) * (days / INTEREST_YEAR_BASIS), 2)


def seed_if_empty():
    """Populate demo data when the database is empty.

    Must be called after db.init_db().  The entire seed runs in a single
    transaction so a partial failure leaves the database unchanged.
    """
    conn = db.get_db()
    try:
        existing_banks = conn.execute("SELECT COUNT(*) FROM banks").fetchone()[0]
        if existing_banks > 0:
            return False

        banks = [
            ("B001", "Bank A"),
            ("B002", "Bank B"),
            ("B003", "Bank C"),
        ]
        for key, name in banks:
            db.upsert_bank(conn, key, name)

        today = date.today()

        credit_lines = [
            {
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

        cl_ids = []
        for payload in credit_lines:
            cl_ids.append(db.create_credit_line(conn, payload))

        advances = [
            {
                "bank": "Bank A",
                "credit_line_id": cl_ids[0],
                "currency": "CHF",
                "amount_original": 80_000_000,
                "start_date": (today - timedelta(days=27)).isoformat(),
                "end_date": (today + timedelta(days=4)).isoformat(),
                "interest_amount": _interest(80_000_000, 31, 1.85),
            },
            {
                "bank": "Bank A",
                "credit_line_id": cl_ids[0],
                "currency": "CHF",
                "amount_original": 55_000_000,
                "start_date": (today - timedelta(days=15)).isoformat(),
                "end_date": (today + timedelta(days=16)).isoformat(),
                "interest_amount": _interest(55_000_000, 31, 1.65),
            },
            {
                "bank": "Bank B",
                "credit_line_id": cl_ids[1],
                "currency": "EUR",
                "amount_original": 62_000_000,
                "start_date": (today - timedelta(days=21)).isoformat(),
                "end_date": (today + timedelta(days=6)).isoformat(),
                "interest_amount": _interest(62_000_000, 27, 2.1),
            },
            {
                "bank": "Bank C",
                "credit_line_id": cl_ids[2],
                "currency": "USD",
                "amount_original": 45_000_000,
                "start_date": (today - timedelta(days=12)).isoformat(),
                "end_date": (today + timedelta(days=10)).isoformat(),
                "interest_amount": _interest(45_000_000, 22, 2.35),
            },
        ]

        for payload in advances:
            payload = dict(payload)
            payload["continuation_date"] = helpers.suggest_continuation_date(payload["end_date"])
            db.create_advance(conn, payload)

        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
