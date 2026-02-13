import sqlite3
import time
from config import DB_PATH, BASE_CURRENCY

SCHEMA = """
CREATE TABLE IF NOT EXISTS banks (
    bank_key TEXT PRIMARY KEY,
    bank_name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS currencies (
    code TEXT PRIMARY KEY,
    css_color TEXT NOT NULL,
    display_order INTEGER NOT NULL,
    ecb_available INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS id_sequences (
    name TEXT PRIMARY KEY,
    last_value INTEGER NOT NULL CHECK(last_value >= 0)
);

CREATE TABLE IF NOT EXISTS credit_lines (
    id TEXT PRIMARY KEY,
    bank_key TEXT NOT NULL,
    description TEXT,
    currency TEXT NOT NULL,
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
    currency TEXT NOT NULL,
    amount_original INTEGER NOT NULL CHECK(amount_original > 0),
    interest_amount REAL NOT NULL CHECK(interest_amount >= 0),
    FOREIGN KEY (credit_line_id) REFERENCES credit_lines(id)
);
"""

# 12-color palette for auto-assigning to new currencies
COLOR_PALETTE = [
    "#0d7c5f",  # green  (CHF default)
    "#2563eb",  # blue   (EUR default)
    "#7c3aed",  # purple (GBP default)
    "#b45309",  # amber  (USD default)
    "#dc2626",  # red
    "#0891b2",  # cyan
    "#c026d3",  # fuchsia
    "#059669",  # emerald
    "#d97706",  # orange
    "#4f46e5",  # indigo
    "#be185d",  # pink
    "#65a30d",  # lime
]

DEFAULT_CURRENCIES = [
    ("CHF", "#0d7c5f", 1, 0),  # base currency — not fetched from ECB
    ("EUR", "#2563eb", 2, 1),
    ("GBP", "#7c3aed", 3, 1),
    ("USD", "#b45309", 4, 1),
    ("CZK", "#dc2626", 5, 1),
    ("PLN", "#0891b2", 6, 1),
]

SEQUENCE_CONFIG = {
    "credit_lines": {"table": "credit_lines", "prefix": "CL", "padding": 3},
    "fixed_advances": {"table": "fixed_advances", "prefix": "FV", "padding": 4},
}

WRITE_RETRY_LIMIT = 3


class WriteBusyError(RuntimeError):
    """Raised when a write transaction cannot acquire a lock after retries."""

    pass


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 3000")
    return conn


def init_db():
    conn = get_db()
    conn.executescript(SCHEMA)
    _seed_currencies(conn)
    _migrate_add_czk_pln(conn)
    _migrate_remove_currency_check(conn)
    _migrate_init_sequences(conn)
    conn.commit()
    conn.close()


def _migrate_add_czk_pln(conn):
    """Add CZK and PLN if not already present."""
    existing = {r[0] for r in conn.execute("SELECT code FROM currencies").fetchall()}
    new_currencies = [c for c in DEFAULT_CURRENCIES if c[0] in ("CZK", "PLN") and c[0] not in existing]
    if new_currencies:
        conn.executemany(
            "INSERT INTO currencies (code, css_color, display_order, ecb_available) VALUES (?, ?, ?, ?)",
            new_currencies,
        )


def _seed_currencies(conn):
    """Insert default currencies if table is empty."""
    count = conn.execute("SELECT COUNT(*) FROM currencies").fetchone()[0]
    if count == 0:
        conn.executemany(
            "INSERT INTO currencies (code, css_color, display_order, ecb_available) VALUES (?, ?, ?, ?)",
            DEFAULT_CURRENCIES,
        )


def _migrate_remove_currency_check(conn):
    """Recreate credit_lines and fixed_advances without CHECK(currency IN (...)).
    Safe to run multiple times — detects if migration already done by checking table SQL.
    """
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='credit_lines'"
    ).fetchone()
    if row is None:
        return  # table doesn't exist yet (fresh DB)
    if "CHECK(currency IN" not in (row[0] or ""):
        return  # already migrated

    conn.executescript("""
        PRAGMA foreign_keys = OFF;

        ALTER TABLE credit_lines RENAME TO _credit_lines_old;
        CREATE TABLE credit_lines (
            id TEXT PRIMARY KEY,
            bank_key TEXT NOT NULL,
            description TEXT,
            currency TEXT NOT NULL,
            amount INTEGER NOT NULL CHECK(amount > 0),
            committed TEXT NOT NULL CHECK(committed IN ('Yes', 'No')),
            start_date TEXT NOT NULL,
            end_date TEXT,
            note TEXT,
            FOREIGN KEY (bank_key) REFERENCES banks(bank_key)
        );
        INSERT INTO credit_lines SELECT * FROM _credit_lines_old;
        DROP TABLE _credit_lines_old;

        ALTER TABLE fixed_advances RENAME TO _fixed_advances_old;
        CREATE TABLE fixed_advances (
            id TEXT PRIMARY KEY,
            bank TEXT NOT NULL,
            credit_line_id TEXT NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            continuation_date TEXT NOT NULL,
            currency TEXT NOT NULL,
            amount_original INTEGER NOT NULL CHECK(amount_original > 0),
            interest_amount REAL NOT NULL CHECK(interest_amount >= 0),
            FOREIGN KEY (credit_line_id) REFERENCES credit_lines(id)
        );
        INSERT INTO fixed_advances SELECT * FROM _fixed_advances_old;
        DROP TABLE _fixed_advances_old;

        PRAGMA foreign_keys = ON;
    """)


def _max_existing_id_number(conn, table_name, prefix):
    rows = conn.execute(f"SELECT id FROM {table_name}").fetchall()
    max_num = 0
    for row in rows:
        value = row["id"]
        if not value or not value.startswith(prefix):
            continue
        suffix = value[len(prefix):]
        if suffix.isdigit():
            max_num = max(max_num, int(suffix))
    return max_num


def _migrate_init_sequences(conn):
    """Create sequence table and backfill values for existing IDs."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS id_sequences ("
        "name TEXT PRIMARY KEY, "
        "last_value INTEGER NOT NULL CHECK(last_value >= 0))"
    )
    for name, cfg in SEQUENCE_CONFIG.items():
        current_max = _max_existing_id_number(conn, cfg["table"], cfg["prefix"])
        conn.execute(
            "INSERT OR IGNORE INTO id_sequences (name, last_value) VALUES (?, ?)",
            (name, current_max),
        )


def _ensure_sequence_row(conn, sequence_name):
    cfg = SEQUENCE_CONFIG.get(sequence_name)
    if not cfg:
        raise ValueError(f"Unknown sequence '{sequence_name}'")
    exists = conn.execute(
        "SELECT 1 FROM id_sequences WHERE name = ?",
        (sequence_name,),
    ).fetchone()
    if exists:
        return
    current_max = _max_existing_id_number(conn, cfg["table"], cfg["prefix"])
    conn.execute(
        "INSERT OR IGNORE INTO id_sequences (name, last_value) VALUES (?, ?)",
        (sequence_name, current_max),
    )


def _next_sequence_value(conn, sequence_name):
    _ensure_sequence_row(conn, sequence_name)
    updated = conn.execute(
        "UPDATE id_sequences SET last_value = last_value + 1 WHERE name = ?",
        (sequence_name,),
    )
    if updated.rowcount != 1:
        raise ValueError(f"Sequence '{sequence_name}' is not initialized")
    row = conn.execute(
        "SELECT last_value FROM id_sequences WHERE name = ?",
        (sequence_name,),
    ).fetchone()
    return row["last_value"]


def _run_in_write_tx(conn, operation):
    for attempt in range(WRITE_RETRY_LIMIT + 1):
        try:
            conn.execute("BEGIN IMMEDIATE")
            result = operation()
            conn.commit()
            return result
        except sqlite3.OperationalError as exc:
            if conn.in_transaction:
                conn.rollback()
            msg = str(exc).lower()
            locked = "database is locked" in msg or "database is busy" in msg
            if locked and attempt < WRITE_RETRY_LIMIT:
                time.sleep(0.05 * (attempt + 1))
                continue
            if locked:
                raise WriteBusyError("Database is busy, please retry") from exc
            raise
        except Exception:
            if conn.in_transaction:
                conn.rollback()
            raise


# ── Currencies ──

def get_currencies(conn):
    return conn.execute(
        "SELECT * FROM currencies ORDER BY display_order"
    ).fetchall()


def add_currency(conn, code, ecb_available=True):
    color = assign_currency_color(conn)
    order = conn.execute("SELECT COALESCE(MAX(display_order), 0) + 1 FROM currencies").fetchone()[0]
    conn.execute(
        "INSERT INTO currencies (code, css_color, display_order, ecb_available) VALUES (?, ?, ?, ?)",
        (code.upper(), color, order, 1 if ecb_available else 0),
    )
    conn.commit()


def delete_currency(conn, code):
    conn.execute("DELETE FROM currencies WHERE code = ?", (code,))
    conn.commit()


def currency_in_use(conn, code):
    """Check if a currency is used by any advance or credit line."""
    row = conn.execute(
        "SELECT COUNT(*) FROM fixed_advances WHERE currency = ? "
        "UNION ALL "
        "SELECT COUNT(*) FROM credit_lines WHERE currency = ?",
        (code, code),
    ).fetchall()
    return any(r[0] > 0 for r in row)


def assign_currency_color(conn):
    """Pick the next unused color from the palette."""
    used = {r["css_color"] for r in conn.execute("SELECT css_color FROM currencies").fetchall()}
    for color in COLOR_PALETTE:
        if color not in used:
            return color
    # All 12 used — cycle back to first
    return COLOR_PALETTE[0]


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
        "SELECT last_value FROM id_sequences WHERE name = 'credit_lines'"
    ).fetchone()
    if row:
        next_value = row["last_value"] + 1
    else:
        next_value = _max_existing_id_number(conn, "credit_lines", "CL") + 1
    return f"CL{next_value:03d}"


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
    def op():
        cfg = SEQUENCE_CONFIG["credit_lines"]
        seq = _next_sequence_value(conn, "credit_lines")
        cl_id = f"{cfg['prefix']}{seq:0{cfg['padding']}d}"
        conn.execute(
            "INSERT INTO credit_lines (id, bank_key, description, currency, amount, committed, start_date, end_date, note) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (cl_id, data["bank_key"], data.get("description"), data["currency"],
             data["amount"], data["committed"], data["start_date"],
             data.get("end_date") or None, data.get("note")),
        )
        return cl_id

    return _run_in_write_tx(conn, op)


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
        "SELECT last_value FROM id_sequences WHERE name = 'fixed_advances'"
    ).fetchone()
    if row:
        next_value = row["last_value"] + 1
    else:
        next_value = _max_existing_id_number(conn, "fixed_advances", "FV") + 1
    return f"FV{next_value:04d}"


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
    def op():
        cfg = SEQUENCE_CONFIG["fixed_advances"]
        seq = _next_sequence_value(conn, "fixed_advances")
        fv_id = f"{cfg['prefix']}{seq:0{cfg['padding']}d}"
        conn.execute(
            "INSERT INTO fixed_advances (id, bank, credit_line_id, start_date, end_date, "
            "continuation_date, currency, amount_original, interest_amount) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (fv_id, data["bank"], data["credit_line_id"], data["start_date"],
             data["end_date"], data["continuation_date"], data["currency"],
             data["amount_original"], data["interest_amount"]),
        )
        return fv_id

    return _run_in_write_tx(conn, op)


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


def get_cl_drawn(conn, cl_id, exclude_fv_id=None):
    if exclude_fv_id:
        row = conn.execute(
            "SELECT cl.amount as facility, COALESCE(SUM(fa.amount_original), 0) as drawn "
            "FROM credit_lines cl "
            "LEFT JOIN fixed_advances fa ON fa.credit_line_id = cl.id "
            "AND fa.start_date <= date('now') AND fa.end_date > date('now') "
            "AND fa.id != ? "
            "WHERE cl.id = ?",
            (exclude_fv_id, cl_id),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT cl.amount as facility, COALESCE(SUM(fa.amount_original), 0) as drawn "
            "FROM credit_lines cl "
            "LEFT JOIN fixed_advances fa ON fa.credit_line_id = cl.id "
            "AND fa.start_date <= date('now') AND fa.end_date > date('now') "
            "WHERE cl.id = ?",
            (cl_id,),
        ).fetchone()
    return dict(row) if row else None


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
