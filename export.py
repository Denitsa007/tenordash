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


def export_xlsx():
    """Export fixed_advances and credit_lines to an xlsx file for Power BI."""
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
        days = calc_days(d["start_date"], d["end_date"])
        rate_pa = calc_interest_rate_pa(d["interest_amount"], d["amount_original"], days)
        ws_fv.append([
            d["id"], d["bank"], d["credit_line_id"], d["currency"],
            d["amount_original"], d["start_date"], d["end_date"],
            d["continuation_date"], d["interest_amount"], days,
            round(rate_pa, 6),
        ])

    # Sheet 2: tblCreditLines
    ws_cl = wb.create_sheet("tblCreditLines")
    ws_cl.append(CREDIT_LINE_COLUMNS)

    for row in credit_lines:
        d = dict(row)
        ws_cl.append([d.get(col) for col in CREDIT_LINE_COLUMNS])

    # Atomic write: write to temp file then rename
    os.makedirs(EXPORT_PATH, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(suffix=".xlsx", dir=EXPORT_PATH)
    os.close(fd)
    try:
        wb.save(tmp_path)
        os.replace(tmp_path, EXPORT_FILE)
    except Exception:
        # Clean up temp file on failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        logger.exception("Failed to write export file")
        raise
