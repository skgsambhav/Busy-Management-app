from flask import Blueprint, render_template, request, jsonify
from datetime import date
import bfe_client
from routes.utils import get_cash_bank_cached

receipts_bp = Blueprint('receipts', __name__)


@receipts_bp.route("/receipt/new")
def receipt_new():
    try:
        cash_bank = get_cash_bank_cached()
        today = date.today().strftime("%Y-%m-%d")
        return render_template("receipt_form.html",
                               cash_bank_accounts=cash_bank,
                               today=today)
    except Exception as e:
        return render_template("error.html", error=str(e))


@receipts_bp.route("/receipts")
def receipt_list():
    try:
        limit = int(request.args.get("limit", 50))
        receipts = bfe_client.get_recent_receipts(limit=limit)
        return render_template("receipt_list.html", receipts=receipts)
    except Exception as e:
        return render_template("error.html", error=str(e))


@receipts_bp.route("/api/receipt/create", methods=["POST"])
def api_create_receipt():
    """Create a receipt voucher via BFE."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400

        required = ["party_code", "cash_bank_code", "amount", "date"]
        for field in required:
            if field not in data:
                return jsonify({"error": f"Missing field: {field}"}), 400

        amount = float(data["amount"])
        if amount <= 0:
            return jsonify({"error": "Amount must be positive"}), 400

        bill_adjustments = data.get("bill_adjustments", [])
        if bill_adjustments:
            total_adj = sum(float(b["amount"]) for b in bill_adjustments)
            if total_adj > amount:
                return jsonify({"error": "Bill adjustment total exceeds receipt amount"}), 400

        result = bfe_client.create_receipt(
            party_code=int(data["party_code"]),
            cash_bank_code=int(data["cash_bank_code"]),
            amount=amount,
            date_str=str(data["date"]),
            narration=str(data.get("narration", "")),
            bill_adjustments=bill_adjustments or None
        )
        return jsonify(result)

    except Exception as e:
        return jsonify({"error": str(e)}), 500
