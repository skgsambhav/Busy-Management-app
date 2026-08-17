from flask import Blueprint, render_template, request, jsonify
import bfe_client

ledger_bp = Blueprint('ledger', __name__)


@ledger_bp.route("/ledger")
def ledger_view():
    try:
        return render_template("ledger.html")
    except Exception as e:
        return render_template("error.html", error=str(e))


@ledger_bp.route("/trial_balance")
def trial_balance_view():
    try:
        return render_template("trial_balance.html")
    except Exception as e:
        return render_template("error.html", error=str(e))


@ledger_bp.route("/api/party/<int:code>/bills")
def api_party_bills(code):
    """Get outstanding bills for a party."""
    try:
        bills = bfe_client.get_outstanding_bills(code)
        return jsonify(bills)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@ledger_bp.route("/api/party/<int:code>/balance")
def api_party_balance(code):
    """Get current balance for a party."""
    try:
        balance = bfe_client.get_party_balance(code)
        return jsonify(balance)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@ledger_bp.route("/api/ledger/<int:code>")
def api_ledger(code):
    """Get full ledger for a party."""
    try:
        ledger = bfe_client.get_ledger(code)
        return jsonify(ledger)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@ledger_bp.route("/api/trial_balance")
def api_trial_balance():
    """Get trial balance for Debtors/Creditors."""
    try:
        tb = bfe_client.get_trial_balance()
        return jsonify(tb)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
