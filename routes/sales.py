from flask import Blueprint, render_template, request, jsonify
import bfe_client
from cachetools import cached, TTLCache
from cachetools import cached, TTLCache

sales_bp = Blueprint('sales', __name__)

@sales_bp.route('/sales_entry')
def sales_page():
    return render_template('sales.html')

@sales_bp.route("/daybook")
def daybook_view():
    try:
        return render_template("daybook.html")
    except Exception as e:
        return render_template("error.html", error=str(e))

@sales_bp.route("/sales")
def sales_vouchers_view():
    try:
        return render_template("sales_vouchers.html")
    except Exception as e:
        return render_template("error.html", error=str(e))

@sales_bp.route('/api/sales/customers')
def api_sales_customers():
    try:
        # Sundry Debtors
        customers = bfe_client.get_parties()
        return jsonify({"success": True, "customers": customers})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@sales_bp.route('/api/sales/items')
def api_sales_items():
    try:
        items = bfe_client.get_items()
        return jsonify({"success": True, "items": items})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@sales_bp.route('/api/sales/pending_bills/<int:party_code>')
def api_sales_pending_bills(party_code):
    try:
        bills = bfe_client.get_outstanding_bills(party_code)
        return jsonify({"success": True, "bills": bills})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@sales_bp.route('/api/sales/submit', methods=['POST'])
def api_sales_submit():
    data = request.json
    try:
        from bridge.sales import create_sales_voucher
        
        customer_code = int(data.get('customer_code'))
        date_str = data.get('date')
        items = data.get('items', [])
        bill_adjustments = data.get('bill_adjustments', [])
        narration = data.get('narration', '')
        stpt = data.get('sale_type', 'L_GST')
        
        stpt_map = {
            'L_GST': 'L/GST',
            'L_B2C': 'L/GST-B2C',
            'I_GST': 'I/GST',
            'L_EXEMPT': 'L/GST-Exempt'
        }
        stpt_name = stpt_map.get(stpt, 'L/GST-Exempt')
        
        total_amt = float(data.get('total_amount', 0))
        
        if not items or total_amt <= 0:
            return jsonify({"success": False, "error": "Invalid items or amount."})
            
        res = bfe_client.create_sales_voucher(
            date_str=date_str,
            customer_code=customer_code,
            items=items,
            total_amount=total_amt,
            narration=narration,
            bill_adjustments=bill_adjustments,
            stpt_name=stpt_name
        )
        
        if res.get("success"):
            return jsonify({"success": True, "vch_code": res["vch_code"], "vch_no": res["vch_no"]})
        else:
            return jsonify({"success": False, "error": res.get("error")})
            
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

_company_info_cache = TTLCache(maxsize=1, ttl=3600)
_daybook_cache = TTLCache(maxsize=10, ttl=10)
_sales_vouchers_cache = TTLCache(maxsize=10, ttl=10)

@cached(_company_info_cache)
def get_company_info_cached():
    return bfe_client.get_company_info()

@cached(_daybook_cache)
def get_daybook_cached(date_str):
    return bfe_client.get_daybook(date_str)

@cached(_sales_vouchers_cache)
def get_sales_vouchers_cached(date_str):
    return bfe_client.get_sales_vouchers(date_str)

@sales_bp.route("/api/daybook")
def api_daybook():
    """Get Day Book transactions for a given date."""
    date_str = request.args.get("date", "").strip()
    try:
        entries = get_daybook_cached(date_str)
        return jsonify(entries)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@sales_bp.route("/api/sales_vouchers")
def api_sales_vouchers():
    """Get Sales Vouchers for a given date."""
    date_str = request.args.get("date", "").strip()
    try:
        vouchers = get_sales_vouchers_cached(date_str)
        return jsonify(vouchers)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@sales_bp.route("/api/sales_voucher/<int:vcode>")
def api_sales_voucher_details(vcode):
    """Get detailed line items for a Sales Voucher."""
    try:
        details = bfe_client.get_sales_voucher_details(vcode)
        return jsonify(details)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@sales_bp.route("/api/company_info")
def api_company_info():
    """Get company information."""
    try:
        info = get_company_info_cached()
        return jsonify(info)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
