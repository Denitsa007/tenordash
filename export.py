import logging
import os
import tempfile

from openpyxl import Workbook

import db
from config import EXPORT_PATH
from helpers import calc_days, calc_interest_rate_pa

logger = logging.getLogger(__name__)

EXPORT_FILE = os.path.join(EXPORT_PATH, "tenordash.xlsx")

ADVANCE_COLUMNS = [
    "id", "bank", "credit_line_id", "currency", "amount_original",
    "start_date", "end_date", "continuation_date", "interest_amount",
    "days", "rate_pa",
]

CREDIT_LINE_COLUMNS = [
    "id", "bank_key", "description", "currency", "amount",
    "committed", "start_date", "end_date", "note", "archived",
]


def _resolve_export_path():
    """Read export_path from DB settings, falling back to config default."""
    try:
        conn = db.get_db()
        try:
            row = conn.execute(
                "SELECT value FROM settings WHERE key = 'export_path'"
            ).fetchone()
            if row and row[0]:
                return row[0]
        finally:
            conn.close()
    except Exception:
        pass
    return EXPORT_PATH


def export_xlsx(export_path=None):
    """Export fixed_advances and credit_lines to an xlsx file for Power BI.

    Args:
        export_path: Optional directory override. If None, reads from DB
                     settings then falls back to config.EXPORT_PATH.
    """
    if export_path is None:
        export_path = _resolve_export_path()

    conn = db.get_db()
    try:
        advances = conn.execute("SELECT * FROM fixed_advances ORDER BY id").fetchall()
        credit_lines = conn.execute("SELECT * FROM credit_lines ORDER BY id").fetchall()
    finally:
        conn.close()

    wb = Workbook()

    # Sheet 1: tblFV (fixed advances with calculated fields)
    ws_fv = wb.active
    ws_fv.title = "tblFV"
    ws_fv.append(ADVANCE_COLUMNS)

    for row in advances:
        d = dict(row)
        try:
            days = calc_days(d["start_date"], d["end_date"])
            rate_pa = calc_interest_rate_pa(d["interest_amount"], d["amount_original"], days)
        except (ValueError, TypeError, KeyError):
            logger.warning("Skipping advance %s: bad date or amount data", d.get("id"))
            days = None
            rate_pa = None
        ws_fv.append([
            d["id"], d["bank"], d["credit_line_id"], d["currency"],
            d["amount_original"], d["start_date"], d["end_date"],
            d["continuation_date"], d["interest_amount"], days,
            round(rate_pa, 6) if rate_pa is not None else None,
        ])

    # Sheet 2: tblCreditLines
    ws_cl = wb.create_sheet("tblCreditLines")
    ws_cl.append(CREDIT_LINE_COLUMNS)

    for row in credit_lines:
        d = dict(row)
        ws_cl.append([d.get(col) for col in CREDIT_LINE_COLUMNS])

    # Atomic write: write to temp file then rename
    export_file = os.path.join(export_path, "tenordash.xlsx")
    os.makedirs(export_path, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(suffix=".xlsx", dir=export_path)
    os.close(fd)
    try:
        wb.save(tmp_path)
        os.replace(tmp_path, export_file)
    except Exception:
        # Clean up temp file on failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        logger.exception("Failed to write export file")
        raise
