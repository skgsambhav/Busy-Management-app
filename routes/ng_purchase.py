"""
Purchase Entry API Routes
"""
from flask import Blueprint, render_template, request, jsonify
import bfe_client

ng_purchase_bp = Blueprint('ng_purchase', __name__)

@ng_purchase_bp.route('/ng_purchase', methods=['GET'])
def ng_purchase_page():
    return render_template('ng_purchase.html')

@ng_purchase_bp.route('/api/ng_purchase/suppliers', methods=['GET'])
def api_ng_purchase_suppliers():
    try:
        suppliers = bfe_client.get_suppliers()
        return jsonify({"success": True, "suppliers": suppliers})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@ng_purchase_bp.route('/api/ng_purchase/items', methods=['GET'])
def api_ng_purchase_items():
    try:
        items = bfe_client.get_items()
        return jsonify({"success": True, "items": items})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@ng_purchase_bp.route('/api/ng_purchase/submit', methods=['POST'])
def api_ng_purchase_submit():
    data = request.json
    try:
        supplier_code = int(data.get('supplier_code'))
        date_str = data.get('date')
        items = data.get('items', [])
        bill_adjustments = data.get('bill_adjustments', [])
        narration = data.get('narration', '')
        stpt = data.get('purc_type', 'L_EXEMPT')
        
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
            
        res = bfe_client.create_purchase_voucher(
            date_str=date_str,
            supplier_code=supplier_code,
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
