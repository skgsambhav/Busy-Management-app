from flask import Blueprint, render_template
from datetime import datetime, date
import bfe_client

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route("/")
def dashboard():
    try:
        # Get recent receipts for the table
        receipts = bfe_client.get_recent_receipts(limit=10)
        
        # Get last 30 days metrics
        from datetime import datetime, timedelta
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)
        
        metrics = bfe_client.get_performance_metrics(
            from_date=start_date.strftime("%Y-%m-%d"),
            to_date=end_date.strftime("%Y-%m-%d")
        )
        
        # Get today's stats from timeline
        today_str = end_date.strftime("%Y-%m-%d")
        today_stats = {"sales": 0, "receipts": 0, "receipts_count": 0, "inflow": 0, "payments": 0, "credit_sales": 0}
        
        if metrics and "timeline" in metrics:
            for day in metrics["timeline"]:
                if day["date"] == today_str:
                    today_stats = day
                    break
                    
        return render_template("dashboard.html",
                               receipts=receipts,
                               metrics=metrics,
                               today_stats=today_stats,
                               now=datetime.now())
    except Exception as e:
        return render_template("error.html", error=str(e))
