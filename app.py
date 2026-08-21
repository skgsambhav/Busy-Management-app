"""Flask app for Busy Receipt Entry System - modular architecture."""

from flask import Flask, render_template
import bfe_client
import atexit
from flask_compress import Compress
from routes import register_blueprints

app = Flask(__name__)
app.secret_key = "busy_receipt_secure_2026"
app.config['JSON_SORT_KEYS'] = False
Compress(app)

# Shutdown BFE bridge on app exit
atexit.register(bfe_client.shutdown)

# Register all route blueprints
register_blueprints(app)

import threading
import time

def warmup_cache():
    """Background thread to pre-fetch heavy datasets on startup."""
    print("Warming up cache in background...", flush=True)
    try:
        from routes.utils import get_parties_cached, get_cash_bank_cached
        from routes.items import get_items_cached
        
        get_cash_bank_cached()
        get_parties_cached()
        get_items_cached()
        print("Cache warmup complete! App is super fast now.", flush=True)
    except Exception as e:
        print(f"Cache warmup failed: {e}", flush=True)

def auto_translate_hindi_background():
    """Background thread to auto translate missing Hindi names for accounts and items on startup."""
    import subprocess, sys, os
    print("Auto-translating missing Hindi names for Accounts & Items in background...", flush=True)
    try:
        py32 = r"C:\Python32\python.exe"
        cmd = [py32, "tools/translate_hindi.py"] if os.path.exists(py32) else [sys.executable, "tools/translate_hindi.py"]
        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
        if res.stdout:
            print(f"[AI Translate]: {res.stdout.strip()}", flush=True)
    except Exception as e:
        print(f"Auto-translation failed: {e}", flush=True)

# Start Scrutiny Runner as a separate 32-bit subprocess for COM compatibility
try:
    import subprocess, sys, os
    _py32 = r"C:\Python32\python.exe"
    _runner = os.path.join(os.path.dirname(__file__), "services", "scrutiny_runner.py")
    if os.path.exists(_py32) and os.path.exists(_runner):
        subprocess.Popen(
            [_py32, _runner],
            cwd=os.path.dirname(__file__),
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
        )
        print("Scrutiny Runner subprocess started (32-bit).", flush=True)
    else:
        print(f"Scrutiny Runner skipped: py32={os.path.exists(_py32)}, runner={os.path.exists(_runner)}", flush=True)
except Exception as e:
    print(f"Failed to start scrutiny runner: {e}")


# -----------------------------------------------------------------------
# Error Pages
# -----------------------------------------------------------------------

@app.errorhandler(404)
def not_found_error(error):
    return render_template('error.html', error="Page not found (404)"), 404

@app.errorhandler(500)
def internal_error(error):
    return render_template('error.html', error=error), 500


if __name__ == "__main__":
    # Ensure bridge is initialized at startup
    from bfe_client import get_company_info
    try:
        get_company_info()
    except Exception as e:
        print(f"Warning: Could not connect to BFE at startup: {e}", flush=True)
        
    print("Starting Busywin App...", flush=True)
    app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)
