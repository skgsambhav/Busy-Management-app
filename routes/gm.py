from flask import Blueprint, render_template, jsonify
from bfe_client import get_pending_dispatch_bills

gm_bp = Blueprint('gm', __name__)

@gm_bp.route('/gm_out')
def gm_out_view():
    """Render the GM-OUT pending dispatch dashboard."""
    return render_template('gm_out.html')

@gm_bp.route('/gm_out/delivered')
def gm_out_delivered_view():
    """Render the GM-OUT delivered dispatches page."""
    return render_template('gm_out_delivered.html')

@gm_bp.route('/api/gm_out/delivered_bills')
def api_get_delivered_bills():
    """API endpoint to get only delivered dispatch bills from DB."""
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id as dispatch_id, date, vch_no as vno, account_name as party_name, 
                   hindi_name, salesman, billed_by, packed_by, invoice_value as total_amount, 
                   status as bill_status, mobile, transporter, total_parcel, delivery_status
            FROM dispatches
            WHERE delivery_status = 'Delivered'
            ORDER BY id DESC
        ''')
        rows = cursor.fetchall()
        conn.close()
        
        data = [dict(row) for row in rows]
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)})

@gm_bp.route('/api/gm_out/pending_bills')
def api_get_pending_dispatch_bills():
    """API endpoint to get pending dispatch bills."""
    try:
        data = get_pending_dispatch_bills()
        
        # Inject dispatch_id and filter out Delivered
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT vch_no, id, delivery_status, transporter, total_parcel FROM dispatches")
        dispatch_map = {row['vch_no']: {'id': row['id'], 'status': row['delivery_status'], 'transporter': row['transporter'], 'total_parcel': row['total_parcel']} for row in cursor.fetchall()}
        conn.close()
        
        filtered_data = []
        for item in data:
            vno = item.get('vno')
            if vno in dispatch_map:
                if dispatch_map[vno]['status'] == 'Delivered':
                    continue # Skip delivered items
                item['dispatch_id'] = dispatch_map[vno]['id']
                item['transporter'] = dispatch_map[vno]['transporter']
                item['total_parcel'] = dispatch_map[vno]['total_parcel']
            filtered_data.append(item)
                
        return jsonify(filtered_data)
    except Exception as e:
        return jsonify({"error": str(e)})

import sqlite3
from flask import request

def get_db():
    conn = sqlite3.connect('dispatches.db')
    conn.row_factory = sqlite3.Row
    return conn

@gm_bp.route('/api/gm_out/dispatch', methods=['GET', 'POST'])
def api_save_dispatch():
    try:
        # Support both GET (query args) and POST (json)
        if request.method == 'POST':
            data = request.json
        else:
            import json
            payload = request.args.get('payload')
            data = json.loads(payload) if payload else {}
            
        conn = get_db()
        cursor = conn.cursor()
        
        vno = data.get('vno')
        cursor.execute("SELECT id FROM dispatches WHERE vch_no = ?", (vno,))
        row = cursor.fetchone()
        
        if row:
            # Update existing
            cursor.execute('''
                UPDATE dispatches 
                SET transporter = ?, total_parcel = ?
                WHERE vch_no = ?
            ''', (data.get('transporter'), data.get('total_parcel'), vno))
            last_id = row['id']
        else:
            # Insert new
            cursor.execute('''
                INSERT INTO dispatches 
                (date, vch_no, account_name, hindi_name, salesman, billed_by, packed_by, invoice_value, status, mobile, transporter, total_parcel, delivery_status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                data.get('date'), vno, data.get('party_name'), data.get('hindi_name'),
                data.get('salesman'), data.get('billed_by'), data.get('packed_by'), data.get('total_amount'),
                data.get('bill_status'), data.get('mobile'), data.get('transporter'), data.get('total_parcel'), 'Pending'
            ))
            last_id = cursor.lastrowid
            
        conn.commit()
        conn.close()
        return jsonify({"success": True, "id": last_id})
    except Exception as e:
        return jsonify({"error": str(e)})

@gm_bp.route('/api/gm_out/delivered/<int:dispatch_id>', methods=['GET', 'POST'])
def api_mark_delivered(dispatch_id):
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute("SELECT vch_no FROM dispatches WHERE id = ?", (dispatch_id,))
        row = cursor.fetchone()
        if not row:
            return jsonify({"error": "Dispatch not found"})
        vno = row['vch_no']
        
        cursor.execute("UPDATE dispatches SET delivery_status = 'Delivered' WHERE id = ?", (dispatch_id,))
        conn.commit()
        conn.close()
        
        # Mark completed in Busy DB
        try:
            import bfe_client
            bfe_client.mark_bill_completed(vno)
        except Exception as e:
            print(f"Warning: Failed to mark busy bill as completed: {e}")
            
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)})

@gm_bp.route('/api/gm_out/delete/<int:dispatch_id>', methods=['GET', 'DELETE'])
def api_delete_dispatch(dispatch_id):
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM dispatches WHERE id = ?", (dispatch_id,))
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)})

@gm_bp.route('/gm_out/print/<int:dispatch_id>')
def print_dispatch(dispatch_id):
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM dispatches WHERE id = ?", (dispatch_id,))
        dispatch = cursor.fetchone()
        conn.close()
        if not dispatch:
            return "Dispatch record not found", 404
        return render_template('dispatch_print.html', dispatch=dict(dispatch))
    except Exception as e:
        return str(e), 500
