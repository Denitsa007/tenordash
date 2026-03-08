import os

import db
import helpers
import import_utils

_SEED_FILE = os.path.join(os.path.dirname(__file__), "Sample Data Synthetic.xlsx")


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

        data = import_utils.parse_excel(_SEED_FILE)

        for bank in data["banks"]["rows"]:
            db.upsert_bank(conn, bank["bank_key"], bank["bank_name"])

        cl_ids = []
        for cl in data["credit_lines"]["rows"]:
            cl_ids.append(db.create_credit_line(conn, cl))

        for adv in data["advances"]["rows"]:
            payload = dict(adv)
            if not payload.get("continuation_date"):
                payload["continuation_date"] = helpers.suggest_continuation_date(
                    payload["end_date"]
                )
            db.create_advance(conn, payload)

        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
