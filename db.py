import sqlite3
from config import DB_PATH, BASE_CURRENCY, EXPORT_PATH

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

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
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


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


DEFAULT_SETTINGS = {
    "display_unit": "millions",
    "export_path": EXPORT_PATH,
    "continuation_limit": "5",
}


def init_db():
    conn = get_db()
    conn.executescript(SCHEMA)
    _seed_currencies(conn)
    _seed_settings(conn)
    _migrate_add_czk_pln(conn)
    _migrate_remove_currency_check(conn)
    _migrate_add_archived_column(conn)
    conn.commit()
    conn.close()


def _seed_settings(conn):
    """Insert any missing default settings without overwriting existing ones."""
    for key, value in DEFAULT_SETTINGS.items():
        conn.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
            (key, value),
        )


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


def _migrate_add_archived_column(conn):
    """Add archived column to credit_lines if not present."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(credit_lines)").fetchall()}
    if "archived" not in cols:
        conn.execute("ALTER TABLE credit_lines ADD COLUMN archived INTEGER NOT NULL DEFAULT 0")


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
        "SELECT id FROM credit_lines ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if not row:
        return "CL001"
    num = int(row["id"][2:]) + 1
    return f"CL{num:03d}"


def get_credit_lines(conn):
    """Return only active (non-archived) credit lines."""
    return conn.execute(
        "SELECT cl.*, b.bank_name FROM credit_lines cl "
        "LEFT JOIN banks b ON cl.bank_key = b.bank_key "
        "WHERE cl.archived = 0 "
        "ORDER BY cl.id"
    ).fetchall()


def get_all_credit_lines(conn):
    """Return all credit lines including archived."""
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


def archive_credit_line(conn, cl_id):
    conn.execute("UPDATE credit_lines SET archived = 1 WHERE id = ?", (cl_id,))
    conn.commit()


def restore_credit_line(conn, cl_id):
    conn.execute("UPDATE credit_lines SET archived = 0 WHERE id = ?", (cl_id,))
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


def get_upcoming_continuations(conn, limit=None):
    """Return the next active advances by continuation_date, with optional limit."""
    sql = (
        "SELECT fa.*, cl.description as cl_description "
        "FROM fixed_advances fa "
        "LEFT JOIN credit_lines cl ON fa.credit_line_id = cl.id "
        "WHERE fa.start_date <= date('now') AND fa.end_date > date('now') "
        "AND fa.continuation_date >= date('now') "
        "ORDER BY fa.continuation_date ASC"
    )
    if limit is not None:
        sql += " LIMIT ?"
        return conn.execute(sql, (limit,)).fetchall()
    return conn.execute(sql).fetchall()


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


def get_continuations_for_month(conn, year, month):
    """Return active advances with continuation_date in the given month."""
    month_start = f"{year:04d}-{month:02d}-01"
    if month == 12:
        month_end = f"{year + 1:04d}-01-01"
    else:
        month_end = f"{year:04d}-{month + 1:02d}-01"
    return conn.execute(
        "SELECT fa.*, cl.description as cl_description "
        "FROM fixed_advances fa "
        "LEFT JOIN credit_lines cl ON fa.credit_line_id = cl.id "
        "WHERE fa.start_date <= date('now') AND fa.end_date > date('now') "
        "AND fa.continuation_date >= ? AND fa.continuation_date < ? "
        "ORDER BY fa.continuation_date ASC",
        (month_start, month_end),
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


def get_setting(conn, key, default=None):
    """Return a single setting value, or default if not found."""
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row[0] if row else default


def set_setting(conn, key, value):
    """Upsert a setting."""
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    conn.commit()


def get_all_settings(conn):
    """Return all settings as a {key: value} dict."""
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    return {r[0]: r[1] for r in rows}


def get_cl_utilization(conn):
    return conn.execute(
        "SELECT cl.id, cl.description, cl.currency, cl.amount as facility_amount, "
        "COALESCE(SUM(fa.amount_original), 0) as drawn_amount "
        "FROM credit_lines cl "
        "LEFT JOIN fixed_advances fa ON fa.credit_line_id = cl.id "
        "AND fa.start_date <= date('now') AND fa.end_date > date('now') "
        "WHERE cl.archived = 0 "
        "GROUP BY cl.id "
        "ORDER BY cl.id"
    ).fetchall()
