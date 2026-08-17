from flask import Blueprint, render_template, jsonify, request
from routes.notification_service import notification_service, get_db

notifications_bp = Blueprint("notifications", __name__)

@notifications_bp.route("/notifications")
def notifications_view():
    try:
        return render_template("weekly_notifications.html")
    except Exception as e:
        return render_template("error.html", error=str(e))

@notifications_bp.route("/api/notifications/settings", methods=["GET"])
def api_get_settings():
    try:
        settings = notification_service.get_settings()
        return jsonify({"success": True, "data": settings})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@notifications_bp.route("/api/notifications/settings", methods=["POST"])
def api_save_settings():
    try:
        settings = request.json or {}
        notification_service.save_settings(settings)
        return jsonify({"success": True, "message": "Settings saved successfully"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@notifications_bp.route("/api/notifications/status", methods=["GET"])
def api_get_status():
    try:
        # Get current running batch if any
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM notification_batches WHERE status IN ('running', 'retrying') ORDER BY id DESC LIMIT 1")
        row = c.fetchone()
        
        batch = None
        if row:
            batch = dict(row)
            
        settings = notification_service.get_settings()
        conn.close()
        
        return jsonify({
            "success": True, 
            "data": {
                "is_running": notification_service.is_running,
                "current_batch": batch,
                "enabled": settings.get("enabled", "0") == "1"
            }
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@notifications_bp.route("/api/notifications/start-batch", methods=["POST"])
def api_start_batch():
    try:
        res = notification_service.start_weekly_batch()
        return jsonify(res)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@notifications_bp.route("/api/notifications/test-message", methods=["POST"])
def api_test_message():
    try:
        from routes.notification_service import build_balance_message
        from bridge.whatsapp import send_whatsapp_message
        
        # Build dummy message
        msg = build_balance_message(
            "TEST CUSTOMER",
            12500.50,
            [
                {"bill_no": "INV/26/001", "date": "10/08/2026", "balance": 5000.0},
                {"bill_no": "INV/26/002", "date": "11/08/2026", "balance": 7500.50}
            ]
        )
        phone = "919752830642"
        res = send_whatsapp_message(phone, msg)
        return jsonify(res)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@notifications_bp.route("/api/notifications/stop-batch", methods=["POST"])
def api_stop_batch():
    try:
        res = notification_service.stop_batch()
        return jsonify(res)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@notifications_bp.route("/api/notifications/retry-failed", methods=["POST"])
def api_retry_failed():
    try:
        batch_id = request.json.get("batch_id")
        if not batch_id:
            return jsonify({"success": False, "error": "Batch ID is required"}), 400
            
        res = notification_service.retry_failed(int(batch_id))
        return jsonify(res)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@notifications_bp.route("/api/notifications/batches", methods=["GET"])
def api_get_batches():
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM notification_batches ORDER BY id DESC LIMIT 20")
        rows = [dict(r) for r in c.fetchall()]
        conn.close()
        return jsonify({"success": True, "data": rows})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@notifications_bp.route("/api/notifications/batch/<int:batch_id>/logs", methods=["GET"])
def api_get_batch_logs(batch_id):
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM notification_logs WHERE batch_id = ? ORDER BY id ASC", (batch_id,))
        rows = [dict(r) for r in c.fetchall()]
        conn.close()
        return jsonify({"success": True, "data": rows})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@notifications_bp.route("/api/notifications/stats", methods=["GET"])
def api_get_stats():
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT SUM(total_customers) as total, SUM(sent_count) as sent, SUM(failed_count) as failed FROM notification_batches")
        row = c.fetchone()
        
        c.execute("SELECT COUNT(*) as total_batches FROM notification_batches")
        batches_row = c.fetchone()
        
        conn.close()
        
        total = row['total'] or 0
        sent = row['sent'] or 0
        failed = row['failed'] or 0
        total_batches = batches_row['total_batches'] or 0
        
        return jsonify({
            "success": True, 
            "data": {
                "total_queued": total,
                "total_sent": sent,
                "total_failed": failed,
                "total_batches": total_batches
            }
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
