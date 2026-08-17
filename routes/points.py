from flask import Blueprint, render_template, request, jsonify
import bfe_client

points_bp = Blueprint('points', __name__)


@points_bp.route("/points")
def points_ledger_view():
    try:
        code = request.args.get("code")
        name = request.args.get("name")
        return render_template("point_ledger.html", selected_code=code, selected_name=name)
    except Exception as e:
        return render_template("error.html", error=str(e))


@points_bp.route("/api/point_ledger_summary")
def api_point_ledger_summary():
    """Get point ledger summary for all contacts."""
    try:
        summary = bfe_client.get_point_ledger_summary()
        return jsonify(summary)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@points_bp.route("/api/point_ledger/<int:code>")
def api_point_ledger(code):
    """Get full point ledger transactions for a contact."""
    try:
        ledger = bfe_client.get_point_ledger(code)
        return jsonify(ledger)
    except Exception as e:
        import traceback
        print(f"Exception in api_point_ledger for {code}: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@points_bp.route("/point_analytics")
def point_analytics_view():
    try:
        return render_template("point_analytics.html")
    except Exception as e:
        return render_template("error.html", error=str(e))

@points_bp.route("/api/point_analytics")
def api_point_analytics():
    """Get full analytics data for points ledger."""
    try:
        import bfe_client
        data = bfe_client.get_point_analytics()
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
