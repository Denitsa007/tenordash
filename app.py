import re
from flask import Flask, render_template, request, jsonify
from datetime import date
from contextlib import contextmanager

import db
import helpers
import ecb
from config import CONTINUATION_ALERT_DAYS, BASE_CURRENCY

app = Flask(__name__)


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


@app.context_processor
def inject_currencies():
    """Make currencies list available in every template."""
    with db_conn() as conn:
        currencies = [dict(r) for r in db.get_currencies(conn)]
        return {"currencies": currencies, "BASE_CURRENCY": BASE_CURRENCY}


# ── Dashboard ──

@app.route("/")
def dashboard():
    with db_conn() as conn:
        totals_rows = db.get_active_totals(conn)
        totals = {r["currency"]: {"total": r["total"], "count": r["count"]} for r in totals_rows}

        alerts = db.get_continuation_alerts(conn, CONTINUATION_ALERT_DAYS)
        alerts = [helpers.enrich_advance(a) for a in alerts]

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
            today=date.today().isoformat(),
        )


# ── Banks ──

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
        lines = db.get_credit_lines(conn)
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
        return jsonify({"ok": True, "id": cl_id})


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
        return jsonify({"ok": True})


@app.route("/credit-lines/<cl_id>", methods=["DELETE"])
def delete_credit_line(cl_id):
    with db_conn() as conn:
        db.delete_credit_line(conn, cl_id)
        return jsonify({"ok": True})


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

    with db_conn() as conn:
        fv_id = db.create_advance(conn, data)
        return jsonify({"ok": True, "id": fv_id})


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

    with db_conn() as conn:
        db.update_advance(conn, fv_id, data)
        return jsonify({"ok": True})


@app.route("/advances/<fv_id>", methods=["DELETE"])
def delete_advance(fv_id):
    with db_conn() as conn:
        db.delete_advance(conn, fv_id)
        return jsonify({"ok": True})


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
        if not info:
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
        return helpers.format_amount_short(int(value))
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
