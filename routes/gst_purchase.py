from flask import Blueprint, render_template, request, jsonify
import bfe_client

gst_purchase_bp = Blueprint('gst_purchase', __name__)

@gst_purchase_bp.route('/gst_purchase', methods=['GET'])
def gst_purchase_page():
    return render_template('gst_purchase.html')

@gst_purchase_bp.route('/api/gst_purchase/suppliers', methods=['GET'])
def api_gst_purchase_suppliers():
    try:
        suppliers = bfe_client.get_suppliers()
        return jsonify({"success": True, "suppliers": suppliers})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@gst_purchase_bp.route('/api/gst_purchase/items', methods=['GET'])
def api_gst_purchase_items():
    try:
        items = bfe_client.get_items()
        return jsonify({"success": True, "items": items})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@gst_purchase_bp.route('/api/gst_purchase/submit', methods=['POST'])
def api_gst_purchase_submit():
    data = request.json
    try:
        supplier_code = int(data.get('supplier_code'))
        date_str = data.get('date')
        items = data.get('items', [])
        bill_adjustments = data.get('bill_adjustments', [])
        narration = data.get('narration', '')
        stpt = data.get('purc_type', 'L_GST')
        
        stpt_map = {
            'L_GST': 'L/GST-ItemWise',
            'I_GST': 'I/GST-ItemWise'
        }
        stpt_name = stpt_map.get(stpt, 'L/GST-ItemWise')
        
        total_amt = float(data.get('total_amount', 0))
        
        if not items or total_amt <= 0:
            return jsonify({"success": False, "error": "Invalid items or amount."})
            
        res = bfe_client.create_gst_purchase_voucher(
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
