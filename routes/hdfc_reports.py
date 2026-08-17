from flask import Blueprint, render_template, request, jsonify
import sqlite3
import os
import json
import sys
import subprocess

hdfc_bp = Blueprint('hdfc_reports', __name__)
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "hdfc_transactions.db")
CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "hdfc_config.json")

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@hdfc_bp.route("/hdfc_transactions", methods=["GET"])
def hdfc_page():
    return render_template("hdfc_transactions.html")

@hdfc_bp.route("/api/hdfc_config", methods=["GET", "POST"])
def hdfc_config():
    if request.method == "POST":
        data = request.json or {}
        email = data.get("email", "").strip()
        app_password = data.get("app_password", "").strip()
        try:
            with open(CONFIG_PATH, "w") as f:
                json.dump({"email": email, "app_password": app_password}, f)
            return jsonify({"success": True})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500
    else:
        # GET
        try:
            if os.path.exists(CONFIG_PATH):
                with open(CONFIG_PATH, "r") as f:
                    config = json.load(f)
                    return jsonify({"email": config.get("email", ""), "has_password": bool(config.get("app_password"))})
        except:
            pass
        return jsonify({"email": "", "has_password": False})

from tools.fetch_hdfc_emails import fetch_and_sync_emails

@hdfc_bp.route("/api/hdfc_sync", methods=["POST"])
def hdfc_sync():
    try:
        days = int(request.args.get("days", 2))
        res = fetch_and_sync_emails(days=days)
        return jsonify(res)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@hdfc_bp.route("/api/hdfc_transactions", methods=["GET"])
def get_transactions():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM transactions ORDER BY date DESC, CAST(email_uid AS INTEGER) DESC")
        rows = cursor.fetchall()
        
        # Group by date
        grouped = {}
        for r in rows:
            dt = r["date"]
            if dt not in grouped:
                grouped[dt] = []
            grouped[dt].append({
                "id": r["id"],
                "amount": r["amount"],
                "sender_name": r["sender_name"],
                "sender_vpa": r["sender_vpa"],
                "upi_ref_no": r["upi_ref_no"]
            })
            
        conn.close()
        
        # Format as list for easier rendering
        result_list = []
        for dt, txns in grouped.items():
            # Format date as DD-MM-YYYY
            parts = dt.split("-")
            disp_date = dt
            if len(parts) == 3:
                disp_date = f"{parts[2]}-{parts[1]}-{parts[0]}"
                
            total = sum(t["amount"] for t in txns)
            result_list.append({
                "date": dt,
                "display_date": disp_date,
                "total_amount": total,
                "transactions": txns
            })
            
        return jsonify({"success": True, "data": result_list})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
