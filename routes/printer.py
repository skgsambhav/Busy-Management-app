from flask import Blueprint, request, jsonify, render_template, current_app
import os
import subprocess
import json
import time
from werkzeug.utils import secure_filename
import threading

printer_bp = Blueprint('printer', __name__)

# Security config for legacy API Key
API_KEY = 'GOPAL_PRINT_API_KEY_2026'

def delete_file_delayed(filepath, delay=6):
    def delayed_delete():
        time.sleep(delay)
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
        except Exception as e:
            print(f"[Print Server] Error deleting temp file: {e}")
            
    threading.Thread(target=delayed_delete).start()

@printer_bp.route('/printer')
def printer_page():
    return render_template('printer.html')

@printer_bp.route('/api/printers', methods=['GET'])
def get_printers():
    ps_command = 'powershell -Command "Get-Printer | Select-Object Name, ShareName, Type, PortName, Shared, PrinterStatus | ConvertTo-Json"'
    try:
        result = subprocess.run(ps_command, capture_output=True, text=True, shell=True)
        if result.returncode != 0:
            return jsonify({"error": "Failed to fetch printers from system."}), 500
        
        output = result.stdout.strip()
        if not output:
            return jsonify([])
            
        printers = json.loads(output)
        if not isinstance(printers, list):
            printers = [printers]
            
        return jsonify(printers)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@printer_bp.route('/api/print', methods=['POST'])
def print_file():
    # Verify Auth for API if requested (Currently allowing all as per local tunnel setup)
    api_key = request.headers.get('x-api-key') or request.args.get('apikey')
    if api_key and api_key != API_KEY:
        return jsonify({"error": "Invalid API Key"}), 401

    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded."}), 400
        
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No file selected."}), 400
        
    printer_name = request.form.get('printer')
    if not printer_name:
        return jsonify({"error": "No printer specified."}), 400
        
    copies = request.form.get('copies', 1, type=int)
    raw = request.form.get('raw', 'false').lower() == 'true'
    share_name = request.form.get('shareName')
    
    # Save file
    uploads_dir = os.path.join(current_app.root_path, 'uploads')
    os.makedirs(uploads_dir, exist_ok=True)
    filename = secure_filename(file.filename)
    filepath = os.path.join(uploads_dir, f"{int(time.time())}_{filename}")
    file.save(filepath)
    
    ext = os.path.splitext(filename)[1].lower()
    
    # Raw ZPL / Label print job
    if raw or ext in ['.zpl', '.txt']:
        if not share_name:
            delete_file_delayed(filepath, 0)
            return jsonify({"error": "Printer share name is required for raw/ZPL printing."}), 400
            
        share_path = f"\\\\localhost\\{share_name}"
        print_cmd = f'cmd.exe /c copy /b "{filepath}" "{share_path}"'
        
        def execute_raw():
            time.sleep(1)
            try:
                subprocess.run(print_cmd, shell=True)
            finally:
                delete_file_delayed(filepath, 0)
                
        threading.Thread(target=execute_raw).start()
        return jsonify({"message": "Raw print job sent successfully."})

    # Standard Document printing (PDF, Images)
    sumatra_exe = os.path.join(current_app.root_path, 'bin', 'SumatraPDF.exe')
    if not os.path.exists(sumatra_exe):
        delete_file_delayed(filepath, 0)
        return jsonify({"error": "SumatraPDF not found in bin directory."}), 500
        
    settings = f"{copies}x,nosel"
    print_cmd = f'"{sumatra_exe}" -print-to "{printer_name}" -print-settings "{settings}" "{filepath}"'
    
    def execute_print(retry_count=0):
        time.sleep(1)
        try:
            result = subprocess.run(print_cmd, shell=True, capture_output=True, text=True)
            if result.returncode != 0:
                print(f"[Print Job] SumatraPDF execution failed: {result.stderr}")
                if retry_count < 2 and ('used by another process' in result.stderr or 'access' in result.stderr):
                    time.sleep(1.5)
                    execute_print(retry_count + 1)
                    return
                delete_file_delayed(filepath, 0)
                return
            
            delete_file_delayed(filepath, 6)
        except Exception as e:
            print(f"[Print Server] System error during printing: {e}")
            delete_file_delayed(filepath, 0)

    threading.Thread(target=execute_print).start()
    return jsonify({"message": "Print job processed successfully."})
