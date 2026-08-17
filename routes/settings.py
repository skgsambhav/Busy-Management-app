from flask import Blueprint, render_template, jsonify, request
import bfe_client

settings_bp = Blueprint("settings", __name__)

@settings_bp.route("/settings/whatsapp")
def settings_whatsapp_view():
    try:
        return render_template("settings_whatsapp.html")
    except Exception as e:
        return render_template("error.html", error=str(e))

@settings_bp.route("/settings/gmail")
def settings_gmail_view():
    try:
        return render_template("settings_gmail.html")
    except Exception as e:
        return render_template("error.html", error=str(e))

@settings_bp.route("/api/settings/whatsapp", methods=["GET"])
def api_get_whatsapp_settings():
    try:
        data = bfe_client.load_whatsapp_settings()
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@settings_bp.route("/api/settings/whatsapp", methods=["POST"])
def api_save_whatsapp_settings():
    try:
        config = request.json or {}
        res = bfe_client.save_whatsapp_settings(config)
        return jsonify(res)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@settings_bp.route("/api/settings/whatsapp/test", methods=["POST"])
def api_test_whatsapp_connection():
    try:
        req_data = request.json or {}
        phone = req_data.get("phone")
        message = req_data.get("message", "Test Connection from Buswin App!")
        if not phone:
            return jsonify({"error": "Phone number is required"}), 400
            
        res = bfe_client.test_whatsapp_connection(phone, message)
        return jsonify(res)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

