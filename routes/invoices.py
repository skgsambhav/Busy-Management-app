"""
invoices.py — Invoice & Ledger R2 Storage + WhatsApp Send Blueprint
Handles: render HTML → upload to R2 → send WhatsApp link to customer
"""

import logging
from flask import Blueprint, request, jsonify, make_response

import bfe_client
from services.r2_store import upload_invoice_html, upload_ledger_html, test_connection, delete_old_objects
from services.invoice_renderer import render_invoice_html
from services.ledger_renderer import render_ledger_html
from bridge.whatsapp import send_whatsapp_message, parse_and_clean_phone_numbers

logger = logging.getLogger(__name__)

invoices_bp = Blueprint("invoices", __name__)


# ═══════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════

from services.whatsapp_messages import (
    _build_invoice_whatsapp_msg,
    _build_receipt_whatsapp_msg,
    _build_ledger_whatsapp_msg
)


def _fmt_amount(val: float) -> str:
    try:
        return f"₹{abs(float(val)):,.2f}"
    except Exception:
        return "₹0.00"


def _parse_date_display(date_str: str) -> str:
    """YYYY-MM-DD → DD/MM/YYYY"""
    if not date_str:
        return ""
    try:
        if "-" in date_str and len(date_str) >= 10:
            p = date_str[:10].split("-")
            return f"{p[2]}/{p[1]}/{p[0]}"
    except Exception:
        pass
    return date_str


# ═══════════════════════════════════════════════════════════════════════════
# INVOICE ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════

@invoices_bp.route("/api/invoice/send", methods=["POST"])
def api_send_invoice():
    """
    Render invoice HTML → Upload to R2 → Send WhatsApp link.
    Body: { "vcode": int, "phone": str (optional - uses party mobile if omitted) }
    """
    data = request.json or {}
    vcode = data.get("vcode")
    phone_override = data.get("phone", "").strip()

    if not vcode:
        return jsonify({"success": False, "error": "vcode is required"}), 400

    try:
        vcode = int(vcode)

        # 1. Fetch voucher data (via bridge)
        voucher = bfe_client.get_sales_voucher_details(vcode)
        if "error" in voucher:
            return jsonify({"success": False, "error": voucher["error"]}), 404

        # 2. Fetch company info
        try:
            company_info = bfe_client.get_company_info()
        except Exception:
            company_info = {}

        # 3. Render premium HTML
        html_content = render_invoice_html(voucher, company_info)

        # 4. Upload to R2
        public_url = upload_invoice_html(vcode, html_content)

        # 5. Determine phone
        phone = phone_override or voucher.get("mobile", "")
        if not phone:
            return jsonify({
                "success": False,
                "error": "No phone number found for this party. Please provide phone manually.",
                "url": public_url,
                "html_uploaded": True
            }), 422

        # 6. Build & send WhatsApp message
        date_display = _parse_date_display(voucher.get("date", ""))
        total_display = _fmt_amount(voucher.get("total_amount", 0))
        party_name = voucher.get("party_name", "Customer")
        vno = voucher.get("vno", str(vcode))

        msg = _build_invoice_whatsapp_msg(vno, date_display, party_name, total_display, public_url)
        wa_result = send_whatsapp_message(phone, msg)

        logger.info(f"[Invoice] Sent vcode={vcode} to {phone} → {public_url}")
        return jsonify({
            "success": True,
            "vcode": vcode,
            "vno": vno,
            "url": public_url,
            "phone": phone,
            "whatsapp": wa_result
        })

    except Exception as e:
        logger.exception(f"[Invoice] Error sending invoice vcode={vcode}: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@invoices_bp.route("/api/invoice/preview/<int:vcode>")
def api_preview_invoice(vcode):
    """
    Render and return the invoice HTML directly in the browser (for testing/preview).
    No R2 upload, no WhatsApp.
    """
    try:
        voucher = bfe_client.get_sales_voucher_details(vcode)
        if "error" in voucher:
            return f"<h2>Error: {voucher['error']}</h2>", 404

        try:
            company_info = bfe_client.get_company_info()
        except Exception:
            company_info = {}

        html_content = render_invoice_html(voucher, company_info)
        response = make_response(html_content)
        response.headers["Content-Type"] = "text/html; charset=utf-8"
        return response

    except Exception as e:
        logger.exception(f"[Invoice Preview] Error: {e}")
        return f"<h2>Error: {e}</h2>", 500


@invoices_bp.route("/api/invoice/upload/<int:vcode>", methods=["POST"])
def api_upload_invoice(vcode):
    """
    Only upload invoice to R2, return URL (no WhatsApp send).
    Useful for generating shareable link on-demand.
    """
    try:
        voucher = bfe_client.get_sales_voucher_details(vcode)
        if "error" in voucher:
            return jsonify({"success": False, "error": voucher["error"]}), 404

        try:
            company_info = bfe_client.get_company_info()
        except Exception:
            company_info = {}

        html_content = render_invoice_html(voucher, company_info)
        public_url = upload_invoice_html(vcode, html_content)

        return jsonify({
            "success": True,
            "vcode": vcode,
            "vno": voucher.get("vno", ""),
            "url": public_url
        })

    except Exception as e:
        logger.exception(f"[Invoice Upload] Error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# ═══════════════════════════════════════════════════════════════════════════
# LEDGER ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════

@invoices_bp.route("/api/ledger/send", methods=["POST"])
def api_send_ledger():
    """
    Render ledger HTML → Upload to R2 → Send WhatsApp link.
    Body: { "party_code": int, "phone": str (optional) }
    """
    data = request.json or {}
    party_code = data.get("party_code")
    phone_override = data.get("phone", "").strip()

    if not party_code:
        return jsonify({"success": False, "error": "party_code is required"}), 400

    try:
        party_code = int(party_code)

        # 1. Fetch all data
        ledger_data = bfe_client.get_ledger(party_code)
        pending_bills = bfe_client.get_outstanding_bills(party_code)

        # 2. Fetch party name from ledger (via bfe master)
        parties = bfe_client.get_parties()
        party_name = ""
        party_name_hi = ""
        party_mobile = ""
        for p in parties:
            if p.get("code") == party_code:
                party_name = p.get("name", "")
                party_name_hi = p.get("name_hi", "") or p.get("name_sl", "")
                party_mobile = p.get("mobile", "")
                break

        try:
            company_info = bfe_client.get_company_info()
        except Exception:
            company_info = {}

        # 3. Render HTML
        html_content = render_ledger_html(
            party_name=party_name,
            party_name_hi=party_name_hi,
            ledger_data=ledger_data,
            pending_bills=pending_bills,
            company_info=company_info
        )

        # 4. Upload to R2
        public_url = upload_ledger_html(party_code, html_content)

        # 5. Determine phone
        phone = phone_override or party_mobile or ledger_data.get("mobile", "")
        if not phone:
            return jsonify({
                "success": False,
                "error": "No phone number found for this party.",
                "url": public_url,
                "html_uploaded": True
            }), 422

        # 6. Calculate net balance for message
        op_bal = float(ledger_data.get("op_bal", 0))
        transactions = ledger_data.get("transactions", [])
        running = op_bal
        for t in transactions:
            running += float(t.get("amount", 0))

        dr_cr = "Dr" if running < 0 else "Cr"
        balance_text = _fmt_amount(running)
        display_name = party_name or "Customer"

        # 7. Send WhatsApp
        msg = _build_ledger_whatsapp_msg(display_name, balance_text, dr_cr, public_url)
        wa_result = send_whatsapp_message(phone, msg)

        logger.info(f"[Ledger] Sent party={party_code} to {phone} → {public_url}")
        return jsonify({
            "success": True,
            "party_code": party_code,
            "party_name": party_name,
            "url": public_url,
            "phone": phone,
            "balance": balance_text,
            "dr_cr": dr_cr,
            "whatsapp": wa_result
        })

    except Exception as e:
        logger.exception(f"[Ledger] Error sending ledger party={party_code}: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@invoices_bp.route("/api/ledger/preview/<int:party_code>")
def api_preview_ledger(party_code):
    """
    Render and return ledger HTML in browser (for preview/testing).
    """
    try:
        ledger_data = bfe_client.get_ledger(party_code)
        pending_bills = bfe_client.get_outstanding_bills(party_code)

        parties = bfe_client.get_parties()
        party_name = ""
        party_name_hi = ""
        for p in parties:
            if p.get("code") == party_code:
                party_name = p.get("name", "")
                party_name_hi = p.get("name_hi", "") or p.get("name_sl", "")
                break

        try:
            company_info = bfe_client.get_company_info()
        except Exception:
            company_info = {}

        html_content = render_ledger_html(
            party_name=party_name,
            party_name_hi=party_name_hi,
            ledger_data=ledger_data,
            pending_bills=pending_bills,
            company_info=company_info
        )
        response = make_response(html_content)
        response.headers["Content-Type"] = "text/html; charset=utf-8"
        return response

    except Exception as e:
        logger.exception(f"[Ledger Preview] Error: {e}")
        return f"<h2>Error: {e}</h2>", 500


@invoices_bp.route("/api/ledger/upload/<int:party_code>", methods=["POST"])
def api_upload_ledger(party_code):
    """Only upload ledger to R2, return URL."""
    try:
        ledger_data = bfe_client.get_ledger(party_code)
        pending_bills = bfe_client.get_outstanding_bills(party_code)

        parties = bfe_client.get_parties()
        party_name, party_name_hi = "", ""
        for p in parties:
            if p.get("code") == party_code:
                party_name = p.get("name", "")
                party_name_hi = p.get("name_hi", "") or p.get("name_sl", "")
                break

        try:
            company_info = bfe_client.get_company_info()
        except Exception:
            company_info = {}

        html_content = render_ledger_html(
            party_name=party_name,
            party_name_hi=party_name_hi,
            ledger_data=ledger_data,
            pending_bills=pending_bills,
            company_info=company_info
        )
        public_url = upload_ledger_html(party_code, html_content)

        return jsonify({
            "success": True,
            "party_code": party_code,
            "party_name": party_name,
            "url": public_url
        })

    except Exception as e:
        logger.exception(f"[Ledger Upload] Error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# ═══════════════════════════════════════════════════════════════════════════
# R2 UTILITY ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════

@invoices_bp.route("/api/r2/test")
def api_r2_test():
    """Test R2 bucket connectivity."""
    result = test_connection()
    return jsonify(result)


@invoices_bp.route("/api/r2/cleanup", methods=["POST"])
def api_r2_cleanup():
    """Manually trigger cleanup of R2 objects older than 30 days."""
    try:
        stats = delete_old_objects()
        return jsonify({"success": True, "stats": stats})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ═══════════════════════════════════════════════════════════════════════════
# BUSY 21 WIN WEBHOOK / SMS DISPATCH
# ═══════════════════════════════════════════════════════════════════════════

@invoices_bp.route("/api/message/busy-send", methods=["GET", "POST"])
@invoices_bp.route("/api/busy/send", methods=["GET", "POST"])
@invoices_bp.route("/api/busy-send", methods=["GET", "POST"])
def api_busy_message_send():
    """Delegate to busy_webhook handler."""
    from routes.busy_webhook import handle_busy_send
    return handle_busy_send()


@invoices_bp.route("/api/busy/dispatches", methods=["GET"])
def api_busy_dispatches_list():
    """Delegate to busy dispatches list."""
    from routes.busy_webhook import get_recent_busy_dispatches
    return get_recent_busy_dispatches()


# ═══════════════════════════════════════════════════════════════════════════
# RECEIPT ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════

@invoices_bp.route("/api/receipt/preview/<int:vcode>")
def api_preview_receipt(vcode):
    """Render and return receipt HTML directly in browser."""
    try:
        from services.receipt_renderer import render_receipt_html
        receipt_data = bfe_client.get_receipt_voucher_details(vcode)
        if "error" in receipt_data:
            return f"<h2>Error: {receipt_data['error']}</h2>", 404

        party_code = receipt_data.get("party_code", 0)
        balance_text = ""
        if party_code:
            try:
                bal_res = bfe_client.get_party_balance(party_code)
                if bal_res:
                    bal_val = bal_res.get("amount", 0)
                    dr_cr = bal_res.get("dr_cr", "Dr")
                    balance_text = f"₹{bal_val:,.2f} {dr_cr}"
            except Exception:
                pass

        try:
            company_info = bfe_client.get_company_info()
        except Exception:
            company_info = {}

        html_content = render_receipt_html(receipt_data, company_info, current_balance=balance_text)
        response = make_response(html_content)
        response.headers["Content-Type"] = "text/html; charset=utf-8"
        return response
    except Exception as e:
        logger.exception(f"[Receipt Preview] Error: {e}")
        return f"<h2>Error: {e}</h2>", 500


@invoices_bp.route("/api/receipt/upload/<int:vcode>", methods=["POST"])
def api_upload_receipt(vcode):
    """Upload digital receipt HTML to R2, return canonical URL."""
    try:
        from services.receipt_renderer import render_receipt_html
        from services.r2_store import upload_receipt_html
        receipt_data = bfe_client.get_receipt_voucher_details(vcode)
        if "error" in receipt_data:
            return jsonify({"success": False, "error": receipt_data["error"]}), 404

        party_code = receipt_data.get("party_code", 0)
        balance_text = ""
        if party_code:
            try:
                bal_res = bfe_client.get_party_balance(party_code)
                if bal_res:
                    bal_val = bal_res.get("amount", 0)
                    dr_cr = bal_res.get("dr_cr", "Dr")
                    balance_text = f"₹{bal_val:,.2f} {dr_cr}"
            except Exception:
                pass

        try:
            company_info = bfe_client.get_company_info()
        except Exception:
            company_info = {}

        html_content = render_receipt_html(receipt_data, company_info, current_balance=balance_text)
        public_url = upload_receipt_html(vcode, html_content)
        return jsonify({
            "success": True,
            "vcode": vcode,
            "vno": receipt_data.get("vno", ""),
            "url": public_url
        })
    except Exception as e:
        logger.exception(f"[Receipt Upload] Error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@invoices_bp.route("/api/receipt/send", methods=["POST"])
def api_send_receipt():
    """Render digital receipt HTML -> Upload to R2 -> Send WhatsApp link."""
    data = request.json or {}
    vcode = data.get("vcode")
    phone_override = data.get("phone", "").strip()
    if not vcode:
        return jsonify({"success": False, "error": "vcode is required"}), 400

    try:
        from services.receipt_renderer import render_receipt_html
        from services.r2_store import upload_receipt_html

        vcode = int(vcode)
        receipt_data = bfe_client.get_receipt_voucher_details(vcode)
        if "error" in receipt_data:
            return jsonify({"success": False, "error": receipt_data["error"]}), 404

        party_code = receipt_data.get("party_code", 0)
        balance_text = ""
        if party_code:
            try:
                bal_res = bfe_client.get_party_balance(party_code)
                if bal_res:
                    bal_val = bal_res.get("amount", 0)
                    dr_cr = bal_res.get("dr_cr", "Dr")
                    balance_text = f"₹{bal_val:,.2f} {dr_cr}"
            except Exception:
                pass

        try:
            company_info = bfe_client.get_company_info()
        except Exception:
            company_info = {}

        html_content = render_receipt_html(receipt_data, company_info, current_balance=balance_text)
        public_url = upload_receipt_html(vcode, html_content)

        phone = phone_override or receipt_data.get("mobile", "")
        if not phone:
            return jsonify({
                "success": False,
                "error": "No phone number found for this party.",
                "url": public_url,
                "html_uploaded": True
            }), 422

        msg = _build_receipt_whatsapp_msg(receipt_data, current_balance=balance_text, url=public_url)
        wa_result = send_whatsapp_message(phone, msg)

        logger.info(f"[Receipt] Sent vcode={vcode} to {phone} -> {public_url}")
        return jsonify({
            "success": True,
            "vcode": vcode,
            "vno": receipt_data.get("vno", ""),
            "url": public_url,
            "phone": phone,
            "whatsapp": wa_result
        })
    except Exception as e:
        logger.exception(f"[Receipt Send] Error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


