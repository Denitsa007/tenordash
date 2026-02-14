from contextlib import contextmanager
from datetime import date
import os
import re

from flask import Flask, g, jsonify, render_template, request

import db
import ecb
import helpers
from config import CONTINUATION_ALERT_DAYS, BASE_CURRENCY
from export import export_xlsx

app = Flask(__name__)


def _try_export(export_path=None):
    """Run export; return warning string on failure, None on success."""
    try:
        export_xlsx(export_path=export_path)
        return None
    except Exception:
        app.logger.exception("Auto-export failed")
        return "Auto-export failed — see server log for details"


@contextmanager
def db_conn():
    conn = db.get_db()
    try:
        yield conn
    finally:
        conn.close()


def parse_json(required_fields=None):
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return None, (jsonify({"ok": False, "error": "Invalid JSON payload"}), 400)

    if required_fields:
        missing = [f for f in required_fields if f not in data]
        if missing:
            return None, (
                jsonify({"ok": False, "error": f"Missing required field(s): {', '.join(missing)}"}),
                400,
            )
    return data, None


def validate_advance_date_order(data):
    try:
        start = date.fromisoformat(data["start_date"])
        end = date.fromisoformat(data["end_date"])
    except (KeyError, TypeError, ValueError):
        return jsonify({"ok": False, "error": "start_date and end_date must be valid ISO dates"}), 400

    if end <= start:
        return jsonify({"ok": False, "error": "end_date must be later than start_date"}), 400
    return None


def build_continuation_calendar(alerts):
    """Build current-month calendar metadata with continuation dates marked."""
    today = date.today()
    month_start = date(today.year, today.month, 1)

    if today.month == 12:
        next_month = date(today.year + 1, 1, 1)
    else:
        next_month = date(today.year, today.month + 1, 1)

    days_in_month = (next_month - month_start).days
    leading_blanks = month_start.weekday()  # Monday=0
    marked_dates = {str(a["continuation_date"]) for a in alerts}

    cells = []
    for _ in range(leading_blanks):
        cells.append({"day": "", "date": None, "marked": False, "today": False})

    for day_num in range(1, days_in_month + 1):
        day_date = date(today.year, today.month, day_num)
        iso = day_date.isoformat()
        cells.append({
            "day": day_num,
            "date": iso,
            "marked": iso in marked_dates,
            "today": day_date == today,
        })

    while len(cells) % 7 != 0:
        cells.append({"day": "", "date": None, "marked": False, "today": False})

    return {
        "month_label": month_start.strftime("%B %Y"),
        "cells": cells,
    }


@app.context_processor
def inject_globals():
    """Make currencies list and settings available in every template."""
    with db_conn() as conn:
        currencies = [dict(r) for r in db.get_currencies(conn)]
        g.settings = db.get_all_settings(conn)
        return {"currencies": currencies, "BASE_CURRENCY": BASE_CURRENCY, "settings": g.settings}


# ── Dashboard ──

@app.route("/")
def dashboard():
    with db_conn() as conn:
        totals_rows = db.get_active_totals(conn)
        totals = {r["currency"]: {"total": r["total"], "count": r["count"]} for r in totals_rows}

        alerts = db.get_continuation_alerts(conn, CONTINUATION_ALERT_DAYS)
        alerts = [helpers.enrich_advance(a) for a in alerts]
        for a in alerts:
            cont = date.fromisoformat(a["continuation_date"])
            a["cont_day"] = cont.day
            a["cont_mon"] = cont.strftime("%b").upper()
            a["cont_weekday"] = cont.strftime("%a")
        continuation_calendar = build_continuation_calendar(alerts)

        active = db.get_active_advances(conn)
        active = [helpers.enrich_advance(a) for a in active]

        utilization = [dict(r) for r in db.get_cl_utilization(conn)]

        currencies = [dict(r) for r in db.get_currencies(conn)]
        fx_rates, rate_date = ecb.get_fx_rates(currencies)

        return render_template(
            "dashboard.html",
            totals=totals,
            alerts=alerts,
            active=active,
            utilization=utilization,
            fx_rates=fx_rates,
            ecb_date=rate_date,
            continuation_calendar=continuation_calendar,
            today=date.today().isoformat(),
        )


# ── Banks ──
# No _try_export() here: banks are not exported to xlsx.  Advances and
# credit lines reference banks by key, which never changes via upsert.

@app.route("/banks")
def banks_page():
    with db_conn() as conn:
        banks = db.get_banks(conn)
        return render_template("banks.html", banks=banks)


@app.route("/banks", methods=["POST"])
def create_bank():
    data, err = parse_json(required_fields=["bank_key", "bank_name"])
    if err:
        return err

    with db_conn() as conn:
        db.upsert_bank(conn, data["bank_key"].strip(), data["bank_name"].strip())
        return jsonify({"ok": True})


@app.route("/banks/<key>", methods=["DELETE"])
def delete_bank(key):
    with db_conn() as conn:
        db.delete_bank(conn, key)
        return jsonify({"ok": True})


# ── Credit Lines ──

@app.route("/credit-lines")
def credit_lines_page():
    with db_conn() as conn:
        lines = db.get_all_credit_lines(conn)
        banks = db.get_banks(conn)
        return render_template("credit_lines.html", lines=lines, banks=banks)


@app.route("/credit-lines", methods=["POST"])
def create_credit_line():
    data, err = parse_json(
        required_fields=["bank_key", "currency", "amount", "committed", "start_date"]
    )
    if err:
        return err

    with db_conn() as conn:
        cl_id = db.create_credit_line(conn, data)
        warn = _try_export()
        resp = {"ok": True, "id": cl_id}
        if warn:
            resp["export_warning"] = warn
        return jsonify(resp)


@app.route("/credit-lines/<cl_id>", methods=["GET"])
def get_credit_line(cl_id):
    with db_conn() as conn:
        row = db.get_credit_line(conn, cl_id)
        if not row:
            return jsonify({"error": "Not found"}), 404
        return jsonify(dict(row))


@app.route("/credit-lines/<cl_id>", methods=["PUT"])
def update_credit_line(cl_id):
    data, err = parse_json(
        required_fields=["bank_key", "currency", "amount", "committed", "start_date"]
    )
    if err:
        return err

    with db_conn() as conn:
        db.update_credit_line(conn, cl_id, data)
        warn = _try_export()
        resp = {"ok": True}
        if warn:
            resp["export_warning"] = warn
        return jsonify(resp)


@app.route("/credit-lines/<cl_id>", methods=["DELETE"])
def archive_credit_line(cl_id):
    with db_conn() as conn:
        db.archive_credit_line(conn, cl_id)
        warn = _try_export()
        resp = {"ok": True}
        if warn:
            resp["export_warning"] = warn
        return jsonify(resp)


@app.route("/credit-lines/<cl_id>/restore", methods=["PATCH"])
def restore_credit_line(cl_id):
    with db_conn() as conn:
        db.restore_credit_line(conn, cl_id)
        warn = _try_export()
        resp = {"ok": True}
        if warn:
            resp["export_warning"] = warn
        return jsonify(resp)


# ── Fixed Advances ──

@app.route("/advances")
def advances_page():
    with db_conn() as conn:
        advances = db.get_advances(conn)
        advances = [helpers.enrich_advance(a) for a in advances]
        banks = db.get_banks(conn)
        lines = db.get_credit_lines(conn)
        return render_template("advances.html", advances=advances, banks=banks, lines=lines)


@app.route("/advances", methods=["POST"])
def create_advance():
    data, err = parse_json(
        required_fields=[
            "bank",
            "credit_line_id",
            "start_date",
            "end_date",
            "continuation_date",
            "currency",
            "amount_original",
            "interest_amount",
        ]
    )
    if err:
        return err
    date_err = validate_advance_date_order(data)
    if date_err:
        return date_err

    with db_conn() as conn:
        fv_id = db.create_advance(conn, data)
        warn = _try_export()
        resp = {"ok": True, "id": fv_id}
        if warn:
            resp["export_warning"] = warn
        return jsonify(resp)


@app.route("/advances/<fv_id>", methods=["GET"])
def get_advance(fv_id):
    with db_conn() as conn:
        row = db.get_advance(conn, fv_id)
        if not row:
            return jsonify({"error": "Not found"}), 404
        return jsonify(helpers.enrich_advance(row))


@app.route("/advances/<fv_id>", methods=["PUT"])
def update_advance(fv_id):
    data, err = parse_json(
        required_fields=[
            "bank",
            "credit_line_id",
            "start_date",
            "end_date",
            "continuation_date",
            "currency",
            "amount_original",
            "interest_amount",
        ]
    )
    if err:
        return err
    date_err = validate_advance_date_order(data)
    if date_err:
        return date_err

    with db_conn() as conn:
        db.update_advance(conn, fv_id, data)
        warn = _try_export()
        resp = {"ok": True}
        if warn:
            resp["export_warning"] = warn
        return jsonify(resp)


@app.route("/advances/<fv_id>", methods=["DELETE"])
def delete_advance(fv_id):
    with db_conn() as conn:
        db.delete_advance(conn, fv_id)
        warn = _try_export()
        resp = {"ok": True}
        if warn:
            resp["export_warning"] = warn
        return jsonify(resp)


# ── API Endpoints ──

@app.route("/api/suggest-continuation")
def suggest_continuation():
    end_date = request.args.get("end_date")
    if not end_date:
        return jsonify({"error": "end_date required"}), 400
    try:
        cont = helpers.suggest_continuation_date(end_date)
        return jsonify({"continuation_date": cont})
    except ValueError:
        return jsonify({"error": "Invalid date"}), 400


@app.route("/api/check-cl-capacity")
def check_cl_capacity():
    cl_id = request.args.get("cl_id")
    try:
        amount = float(request.args.get("amount", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "amount must be numeric"}), 400
    exclude = request.args.get("exclude")
    if not cl_id:
        return jsonify({"error": "cl_id required"}), 400
    with db_conn() as conn:
        info = db.get_cl_drawn(conn, cl_id, exclude_fv_id=exclude)
        if not info or info.get("facility") is None:
            return jsonify({"error": "Credit line not found"}), 404
        new_drawn = info["drawn"] + amount
        exceeded = new_drawn > info["facility"]
        return jsonify({
            "facility": info["facility"],
            "current_drawn": info["drawn"],
            "new_drawn": new_drawn,
            "exceeded": exceeded,
        })


@app.route("/api/ecb-rate")
def ecb_rate():
    with db_conn() as conn:
        currencies = [dict(r) for r in db.get_currencies(conn)]
        rates, rate_date = ecb.get_fx_rates(currencies)
        return jsonify({"rates": rates, "date": rate_date})


# ── Currency Management API ──

@app.route("/api/currencies")
def list_currencies():
    with db_conn() as conn:
        rows = db.get_currencies(conn)
        return jsonify([dict(r) for r in rows])


@app.route("/api/currencies", methods=["POST"])
def add_currency():
    data, err = parse_json(required_fields=["code"])
    if err:
        return err
    code = (data.get("code") or "").strip().upper()
    if not re.match(r"^[A-Z]{3}$", code):
        return jsonify({"ok": False, "error": "Currency code must be exactly 3 letters"}), 400

    with db_conn() as conn:
        # Check if already exists
        existing = conn.execute("SELECT code FROM currencies WHERE code = ?", (code,)).fetchone()
        if existing:
            return jsonify({"ok": False, "error": f"{code} already exists"}), 409

        # Validate against ECB
        ecb_ok, ecb_msg = ecb.validate_currency_ecb(code)

        db.add_currency(conn, code, ecb_available=ecb_ok)

        # Clear ECB cache so new currency is included in next fetch
        ecb.clear_cache()

        return jsonify({
            "ok": True,
            "code": code,
            "ecb_available": ecb_ok,
            "ecb_warning": ecb_msg,
        })


@app.route("/api/currencies/<code>", methods=["DELETE"])
def remove_currency(code):
    code = code.upper()
    if code == BASE_CURRENCY:
        return jsonify({"ok": False, "error": f"Cannot delete base currency ({BASE_CURRENCY})"}), 400

    with db_conn() as conn:
        if db.currency_in_use(conn, code):
            return jsonify({"ok": False, "error": f"{code} is in use by advances or credit lines"}), 409

        db.delete_currency(conn, code)
        ecb.clear_cache()
        return jsonify({"ok": True})


# ── Settings API ──

VALID_DISPLAY_UNITS = {"full", "thousands", "millions"}


@app.route("/api/settings")
def list_settings():
    with db_conn() as conn:
        return jsonify(db.get_all_settings(conn))


@app.route("/api/settings", methods=["PUT"])
def update_setting():
    data, err = parse_json(required_fields=["key", "value"])
    if err:
        return err

    key = data["key"]
    value = data["value"]

    if not isinstance(value, str) or not value.strip():
        return jsonify({"ok": False, "error": "Value must be a non-empty string"}), 400

    if key == "display_unit":
        if value not in VALID_DISPLAY_UNITS:
            return jsonify({"ok": False, "error": f"display_unit must be one of: {', '.join(sorted(VALID_DISPLAY_UNITS))}"}), 400

    elif key == "export_path":
        path = os.path.expanduser(value)
        if not os.path.isabs(path):
            return jsonify({"ok": False, "error": "Export path must be an absolute path"}), 400
        if not os.path.isdir(path):
            return jsonify({"ok": False, "error": "Directory does not exist"}), 400
        if not os.access(path, os.W_OK):
            return jsonify({"ok": False, "error": "Directory is not writable"}), 400
        value = path

    else:
        return jsonify({"ok": False, "error": f"Unknown setting: {key}"}), 400

    with db_conn() as conn:
        db.set_setting(conn, key, value)

    # Trigger re-export with the new path so the file lands there immediately
    if key == "export_path":
        _try_export(export_path=value)

    return jsonify({"ok": True})


# ── Template Helpers ──

@app.template_filter("amount")
def amount_filter(value):
    try:
        return f"{int(value):,}"
    except (ValueError, TypeError):
        return value


@app.template_filter("amount_short")
def amount_short_filter(value):
    try:
        v = int(value)
        unit = getattr(g, 'settings', {}).get("display_unit", "millions")
        if unit == "full":
            return f"{v:,}"
        if unit == "thousands":
            return helpers.format_amount_thousands(v)
        return helpers.format_amount_short(v)
    except (ValueError, TypeError):
        return value


@app.template_filter("rate")
def rate_filter(value):
    try:
        return f"{float(value):.4f}%"
    except (ValueError, TypeError):
        return value


@app.template_filter("date_display")
def date_display_filter(value):
    if not value:
        return ""
    try:
        d = date.fromisoformat(value)
        return d.strftime("%b %d, %Y")
    except ValueError:
        return value


if __name__ == "__main__":
    db.init_db()
    app.run(debug=True, port=5001)
