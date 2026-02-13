from flask import Flask, render_template, request, jsonify
from datetime import date

import db
import helpers
import ecb
from config import CONTINUATION_ALERT_DAYS

app = Flask(__name__)


@app.before_request
def before_request():
    pass


# ── Dashboard ──

@app.route("/")
def dashboard():
    conn = db.get_db()
    try:
        totals_rows = db.get_active_totals(conn)
        totals = {r["currency"]: {"total": r["total"], "count": r["count"]} for r in totals_rows}

        alerts = db.get_continuation_alerts(conn, CONTINUATION_ALERT_DAYS)
        alerts = [helpers.enrich_advance(a) for a in alerts]

        active = db.get_active_advances(conn)
        active = [helpers.enrich_advance(a) for a in active]

        utilization = [dict(r) for r in db.get_cl_utilization(conn)]

        rate, rate_date = ecb.get_eur_chf_rate()

        return render_template(
            "dashboard.html",
            totals=totals,
            alerts=alerts,
            active=active,
            utilization=utilization,
            ecb_rate=rate,
            ecb_date=rate_date,
            today=date.today().isoformat(),
        )
    finally:
        conn.close()


# ── Banks ──

@app.route("/banks")
def banks_page():
    conn = db.get_db()
    try:
        banks = db.get_banks(conn)
        return render_template("banks.html", banks=banks)
    finally:
        conn.close()


@app.route("/banks", methods=["POST"])
def create_bank():
    data = request.get_json()
    conn = db.get_db()
    try:
        db.upsert_bank(conn, data["bank_key"].strip(), data["bank_name"].strip())
        return jsonify({"ok": True})
    finally:
        conn.close()


@app.route("/banks/<key>", methods=["DELETE"])
def delete_bank(key):
    conn = db.get_db()
    try:
        db.delete_bank(conn, key)
        return jsonify({"ok": True})
    finally:
        conn.close()


# ── Credit Lines ──

@app.route("/credit-lines")
def credit_lines_page():
    conn = db.get_db()
    try:
        lines = db.get_credit_lines(conn)
        banks = db.get_banks(conn)
        return render_template("credit_lines.html", lines=lines, banks=banks)
    finally:
        conn.close()


@app.route("/credit-lines", methods=["POST"])
def create_credit_line():
    data = request.get_json()
    conn = db.get_db()
    try:
        cl_id = db.create_credit_line(conn, data)
        return jsonify({"ok": True, "id": cl_id})
    finally:
        conn.close()


@app.route("/credit-lines/<cl_id>", methods=["GET"])
def get_credit_line(cl_id):
    conn = db.get_db()
    try:
        row = db.get_credit_line(conn, cl_id)
        if not row:
            return jsonify({"error": "Not found"}), 404
        return jsonify(dict(row))
    finally:
        conn.close()


@app.route("/credit-lines/<cl_id>", methods=["PUT"])
def update_credit_line(cl_id):
    data = request.get_json()
    conn = db.get_db()
    try:
        db.update_credit_line(conn, cl_id, data)
        return jsonify({"ok": True})
    finally:
        conn.close()


@app.route("/credit-lines/<cl_id>", methods=["DELETE"])
def delete_credit_line(cl_id):
    conn = db.get_db()
    try:
        db.delete_credit_line(conn, cl_id)
        return jsonify({"ok": True})
    finally:
        conn.close()


# ── Fixed Advances ──

@app.route("/advances")
def advances_page():
    conn = db.get_db()
    try:
        advances = db.get_advances(conn)
        advances = [helpers.enrich_advance(a) for a in advances]
        banks = db.get_banks(conn)
        lines = db.get_credit_lines(conn)
        return render_template("advances.html", advances=advances, banks=banks, lines=lines)
    finally:
        conn.close()


@app.route("/advances", methods=["POST"])
def create_advance():
    data = request.get_json()
    conn = db.get_db()
    try:
        fv_id = db.create_advance(conn, data)
        return jsonify({"ok": True, "id": fv_id})
    finally:
        conn.close()


@app.route("/advances/<fv_id>", methods=["GET"])
def get_advance(fv_id):
    conn = db.get_db()
    try:
        row = db.get_advance(conn, fv_id)
        if not row:
            return jsonify({"error": "Not found"}), 404
        return jsonify(helpers.enrich_advance(row))
    finally:
        conn.close()


@app.route("/advances/<fv_id>", methods=["PUT"])
def update_advance(fv_id):
    data = request.get_json()
    conn = db.get_db()
    try:
        db.update_advance(conn, fv_id, data)
        return jsonify({"ok": True})
    finally:
        conn.close()


@app.route("/advances/<fv_id>", methods=["DELETE"])
def delete_advance(fv_id):
    conn = db.get_db()
    try:
        db.delete_advance(conn, fv_id)
        return jsonify({"ok": True})
    finally:
        conn.close()


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


@app.route("/api/ecb-rate")
def ecb_rate():
    rate, rate_date = ecb.get_eur_chf_rate()
    return jsonify({"rate": rate, "date": rate_date})


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
