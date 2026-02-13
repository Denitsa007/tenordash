import sqlite3
from config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS banks (
    bank_key TEXT PRIMARY KEY,
    bank_name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS credit_lines (
    id TEXT PRIMARY KEY,
    bank_key TEXT NOT NULL,
    description TEXT,
    currency TEXT NOT NULL CHECK(currency IN ('CHF', 'EUR')),
    amount INTEGER NOT NULL CHECK(amount > 0),
    committed TEXT NOT NULL CHECK(committed IN ('Yes', 'No')),
    start_date TEXT NOT NULL,
    end_date TEXT,
    note TEXT,
    FOREIGN KEY (bank_key) REFERENCES banks(bank_key)
);

CREATE TABLE IF NOT EXISTS fixed_advances (
    id TEXT PRIMARY KEY,
    bank TEXT NOT NULL,
    credit_line_id TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    continuation_date TEXT NOT NULL,
    currency TEXT NOT NULL CHECK(currency IN ('CHF', 'EUR')),
    amount_original INTEGER NOT NULL CHECK(amount_original > 0),
    interest_amount REAL NOT NULL CHECK(interest_amount >= 0),
    FOREIGN KEY (credit_line_id) REFERENCES credit_lines(id)
);
"""


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db()
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


# ── Banks ──

def get_banks(conn):
    return conn.execute("SELECT * FROM banks ORDER BY bank_name").fetchall()


def get_bank(conn, bank_key):
    return conn.execute("SELECT * FROM banks WHERE bank_key = ?", (bank_key,)).fetchone()


def upsert_bank(conn, bank_key, bank_name):
    conn.execute(
        "INSERT INTO banks (bank_key, bank_name) VALUES (?, ?) "
        "ON CONFLICT(bank_key) DO UPDATE SET bank_name = excluded.bank_name",
        (bank_key, bank_name),
    )
    conn.commit()


def delete_bank(conn, bank_key):
    conn.execute("DELETE FROM banks WHERE bank_key = ?", (bank_key,))
    conn.commit()


# ── Credit Lines ──

def next_cl_id(conn):
    row = conn.execute(
        "SELECT id FROM credit_lines ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if not row:
        return "CL001"
    num = int(row["id"][2:]) + 1
    return f"CL{num:03d}"


def get_credit_lines(conn):
    return conn.execute(
        "SELECT cl.*, b.bank_name FROM credit_lines cl "
        "LEFT JOIN banks b ON cl.bank_key = b.bank_key "
        "ORDER BY cl.id"
    ).fetchall()


def get_credit_line(conn, cl_id):
    return conn.execute(
        "SELECT cl.*, b.bank_name FROM credit_lines cl "
        "LEFT JOIN banks b ON cl.bank_key = b.bank_key "
        "WHERE cl.id = ?", (cl_id,)
    ).fetchone()


def create_credit_line(conn, data):
    cl_id = next_cl_id(conn)
    conn.execute(
        "INSERT INTO credit_lines (id, bank_key, description, currency, amount, committed, start_date, end_date, note) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (cl_id, data["bank_key"], data.get("description"), data["currency"],
         data["amount"], data["committed"], data["start_date"],
         data.get("end_date") or None, data.get("note")),
    )
    conn.commit()
    return cl_id


def update_credit_line(conn, cl_id, data):
    conn.execute(
        "UPDATE credit_lines SET bank_key=?, description=?, currency=?, amount=?, "
        "committed=?, start_date=?, end_date=?, note=? WHERE id=?",
        (data["bank_key"], data.get("description"), data["currency"],
         data["amount"], data["committed"], data["start_date"],
         data.get("end_date") or None, data.get("note"), cl_id),
    )
    conn.commit()


def delete_credit_line(conn, cl_id):
    conn.execute("DELETE FROM credit_lines WHERE id = ?", (cl_id,))
    conn.commit()


# ── Fixed Advances ──

def next_fv_id(conn):
    row = conn.execute(
        "SELECT id FROM fixed_advances ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if not row:
        return "FV0001"
    num = int(row["id"][2:]) + 1
    return f"FV{num:04d}"


def get_advances(conn):
    return conn.execute(
        "SELECT fa.*, cl.description as cl_description "
        "FROM fixed_advances fa "
        "LEFT JOIN credit_lines cl ON fa.credit_line_id = cl.id "
        "ORDER BY fa.start_date DESC, fa.id DESC"
    ).fetchall()


def get_advance(conn, fv_id):
    return conn.execute(
        "SELECT fa.*, cl.description as cl_description "
        "FROM fixed_advances fa "
        "LEFT JOIN credit_lines cl ON fa.credit_line_id = cl.id "
        "WHERE fa.id = ?", (fv_id,)
    ).fetchone()


def create_advance(conn, data):
    fv_id = next_fv_id(conn)
    conn.execute(
        "INSERT INTO fixed_advances (id, bank, credit_line_id, start_date, end_date, "
        "continuation_date, currency, amount_original, interest_amount) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (fv_id, data["bank"], data["credit_line_id"], data["start_date"],
         data["end_date"], data["continuation_date"], data["currency"],
         data["amount_original"], data["interest_amount"]),
    )
    conn.commit()
    return fv_id


def update_advance(conn, fv_id, data):
    conn.execute(
        "UPDATE fixed_advances SET bank=?, credit_line_id=?, start_date=?, end_date=?, "
        "continuation_date=?, currency=?, amount_original=?, interest_amount=? WHERE id=?",
        (data["bank"], data["credit_line_id"], data["start_date"],
         data["end_date"], data["continuation_date"], data["currency"],
         data["amount_original"], data["interest_amount"], fv_id),
    )
    conn.commit()


def delete_advance(conn, fv_id):
    conn.execute("DELETE FROM fixed_advances WHERE id = ?", (fv_id,))
    conn.commit()


# ── Dashboard Queries ──

def get_active_advances(conn):
    return conn.execute(
        "SELECT fa.*, cl.description as cl_description "
        "FROM fixed_advances fa "
        "LEFT JOIN credit_lines cl ON fa.credit_line_id = cl.id "
        "WHERE fa.start_date <= date('now') AND fa.end_date > date('now') "
        "ORDER BY fa.continuation_date ASC"
    ).fetchall()


def get_active_totals(conn):
    return conn.execute(
        "SELECT currency, SUM(amount_original) as total, COUNT(*) as count "
        "FROM fixed_advances "
        "WHERE start_date <= date('now') AND end_date > date('now') "
        "GROUP BY currency"
    ).fetchall()


def get_continuation_alerts(conn, days=7):
    return conn.execute(
        "SELECT fa.*, cl.description as cl_description "
        "FROM fixed_advances fa "
        "LEFT JOIN credit_lines cl ON fa.credit_line_id = cl.id "
        "WHERE fa.start_date <= date('now') AND fa.end_date > date('now') "
        "AND fa.continuation_date <= date('now', '+' || ? || ' days') "
        "AND fa.continuation_date >= date('now') "
        "ORDER BY fa.continuation_date ASC",
        (days,),
    ).fetchall()


def get_cl_utilization(conn):
    return conn.execute(
        "SELECT cl.id, cl.description, cl.currency, cl.amount as facility_amount, "
        "COALESCE(SUM(fa.amount_original), 0) as drawn_amount "
        "FROM credit_lines cl "
        "LEFT JOIN fixed_advances fa ON fa.credit_line_id = cl.id "
        "AND fa.start_date <= date('now') AND fa.end_date > date('now') "
        "GROUP BY cl.id "
        "ORDER BY cl.id"
    ).fetchall()
