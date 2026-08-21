"""
Routes package - Flask Blueprint registration.
"""

from routes.dashboard import dashboard_bp
from routes.receipts import receipts_bp
from routes.ledger import ledger_bp
from routes.sales import sales_bp
from routes.items import items_bp
from routes.points import points_bp
from routes.analyzer import analyzer_bp
from routes.utils import utils_bp
from routes.settings import settings_bp
from routes.hdfc_reports import hdfc_bp
from routes.notifications import notifications_bp
from routes.printer import printer_bp
from routes.translator import translator_bp
from routes.gm import gm_bp
from routes.invoices import invoices_bp

def register_blueprints(app):
    """Register all blueprints with the Flask app."""
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(receipts_bp)
    app.register_blueprint(ledger_bp)
    app.register_blueprint(sales_bp)
    app.register_blueprint(items_bp)
    app.register_blueprint(points_bp)
    app.register_blueprint(analyzer_bp)
    app.register_blueprint(utils_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(hdfc_bp)
    app.register_blueprint(notifications_bp)
    app.register_blueprint(printer_bp)
    app.register_blueprint(translator_bp)
    app.register_blueprint(gm_bp)
    app.register_blueprint(invoices_bp)
    
    from routes.ng_purchase import ng_purchase_bp
    from routes.gst_purchase import gst_purchase_bp
    from routes.print_routes import print_bp
    from routes.busy_webhook import busy_webhook_bp
    
    app.register_blueprint(ng_purchase_bp)
    app.register_blueprint(gst_purchase_bp)
    app.register_blueprint(print_bp)
    app.register_blueprint(busy_webhook_bp)

