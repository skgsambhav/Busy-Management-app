import sys
import os
import time
import sqlite3
import datetime
import threading
import logging
import winsound
import webview
from flask import Flask, render_template, jsonify, request

# Ensure we can find the project root and import bridge/config
if getattr(sys, 'frozen', False):
    PROJECT_DIR = r"C:\Users\GOPAL MARKETING\Desktop\BUSY\receipt_app"
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    PROJECT_DIR = os.path.dirname(BASE_DIR)

sys.path.insert(0, PROJECT_DIR)

DB_PATH = os.path.join(PROJECT_DIR, "data", "approvals.db")
LOG_PATH = os.path.join(PROJECT_DIR, "data", "web_app.log")
logging.basicConfig(filename=LOG_PATH, level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logging.info("Starting Web-Based Voucher Approval Utility...")

if getattr(sys, 'frozen', False):
    template_dir = os.path.join(sys._MEIPASS, "tools", "templates")
else:
    template_dir = os.path.join(PROJECT_DIR, "tools", "templates")

app = Flask(__name__, template_folder=template_dir)

# Global State
bfe_active = False
get_rs_func = None
last_beep_time = 0
prev_unapproved_count = 0
vouchers_cache = {}  # vcode -> {vchno, amount, ...}

def init_db():
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('PRAGMA journal_mode=WAL;')
        c.execute('''
            CREATE TABLE IF NOT EXISTS approvals (
                vchcode INTEGER PRIMARY KEY,
                vchno TEXT,
                amount REAL,
                status TEXT,
                approved_at TIMESTAMP
            )
        ''')
        try:
            c.execute("ALTER TABLE approvals ADD COLUMN approval_count INTEGER DEFAULT 0")
            c.execute("ALTER TABLE approvals ADD COLUMN previous_amount REAL DEFAULT 0")
        except sqlite3.OperationalError:
            pass
        conn.commit()
        conn.close()
    except sqlite3.Error as e:
        logging.error(f"Database Initialization Error: {e}")

def init_bfe():
    global bfe_active, get_rs_func
    while True:
        try:
            from bridge.connection import initialize_bfe, _get_rs
            initialize_bfe()
            get_rs_func = _get_rs
            bfe_active = True
            logging.info("BFE Successfully Connected")
            break
        except Exception as e:
            logging.error(f"BFE Initialization Error: {e}")
            bfe_active = False
            time.sleep(10)

@app.route('/')
def index():
    return render_template('voucher_approval.html')

@app.route('/api/status')
def status():
    return jsonify({"bfe_active": bfe_active})

@app.route('/api/data')
def get_data():
    global bfe_active, prev_unapproved_count, last_beep_time, vouchers_cache
    if not bfe_active or not get_rs_func:
        return jsonify({"success": False, "error": "BFE Not Connected"})
        
    try:
        today_date = datetime.date.today().strftime("%m/%d/%Y")
        sql = f"""
            SELECT t1.VchCode, t1.VchNo, t1.Date, t1.VchAmtBaseCur, c.UserName, c.ActionTime AS VchTime, m.Name AS MasterParty, bd.PartyName AS BillParty
            FROM (((Tran1 t1
            LEFT JOIN CheckList c ON (t1.VchCode = c.Code AND c.Type = 2 AND c.Action = 1))
            LEFT JOIN Master1 m ON t1.MasterCode1 = m.Code)
            LEFT JOIN BillingDet bd ON t1.VchCode = bd.VchCode)
            WHERE t1.VchType = 9 AND t1.Date = #{today_date}#
        """
        
        try:
            rs = get_rs_func(sql)
        except Exception as e:
            logging.error(f"BFE Connection Lost during fetch: {e}")
            bfe_active = False
            threading.Thread(target=init_bfe, daemon=True).start()
            return jsonify({"success": False, "error": "BFE Disconnected during fetch"})

        def safe_val(field_name, default=""):
            try:
                val = rs.Fields(field_name).Value
                return val if val is not None else default
            except Exception:
                return default

        vouchers_cache.clear()
        
        while not rs.EOF:
            vcode = int(safe_val('VchCode', 0))
            vchno = str(safe_val('VchNo', "")).strip()
            raw_date = str(safe_val('Date', ""))[:10]
            if raw_date and "-" in raw_date:
                parts = raw_date.split("-")
                if len(parts) == 3:
                    raw_date = f"{parts[2]}-{parts[1]}-{parts[0]}"
            elif raw_date and "/" in raw_date:
                parts = raw_date.split("/")
                if len(parts) == 3:
                    raw_date = f"{parts[0]}-{parts[1]}-{parts[2]}"
            
            amt = float(safe_val('VchAmtBaseCur', 0))
            creator = str(safe_val('UserName', "Admin")).strip()
            vch_time_raw = str(safe_val('VchTime', "")).strip()
            if vch_time_raw:
                try:
                    # BFE returns time as datetime string like "2026-08-28 15:13:51+00:00"
                    if " " in vch_time_raw:
                        time_part = vch_time_raw.split(" ")[1]
                        if "+" in time_part:
                            time_part = time_part.split("+")[0]
                        # Convert 24hr to 12hr format
                        t_obj = datetime.datetime.strptime(time_part, "%H:%M:%S")
                        vch_time = t_obj.strftime("%I:%M %p")
                        raw_date = f"{raw_date} {vch_time}"
                except Exception:
                    pass
            
            master_party = str(safe_val('MasterParty', "")).strip()
            bill_party = str(safe_val('BillParty', "")).strip()
            party_name = bill_party if bill_party else master_party
            if not party_name:
                party_name = "Unknown"
            
            vouchers_cache[vcode] = {"vchno": vchno, "date": raw_date, "party": party_name, "amount": amt, "creator": creator}
            rs.MoveNext()
        rs.Close()
        
        try:
            conn = sqlite3.connect(DB_PATH, timeout=5.0)
            c = conn.cursor()
            c.execute("SELECT vchcode, amount, status, previous_amount, approval_count FROM approvals")
            db_records = {row[0]: {"amount": row[1], "status": row[2], "prev": row[3] or 0, "count": row[4] or 0} for row in c.fetchall()}
            conn.close()
        except sqlite3.Error as e:
            logging.error(f"SQLite Read Error: {e}")
            db_records = {}
        
        unapproved = []
        approved = []
        
        for vcode, info in vouchers_cache.items():
            if vcode not in db_records:
                unapproved.append((vcode, info["vchno"], info["date"], info["party"], info["creator"], "-", info["amount"], 0, "Unapproved"))
            else:
                db_rec = db_records[vcode]
                if db_rec["status"] == "APPROVED" and abs(db_rec["amount"] - info["amount"]) < 0.01:
                    prev_amt = db_rec["prev"] if db_rec["count"] > 1 else "-"
                    approved.append((vcode, info["vchno"], info["date"], info["party"], info["creator"], prev_amt, info["amount"], db_rec["count"], "Approved"))
                elif db_rec["status"] != "APPROVED":
                    prev_amt = db_rec["prev"] if db_rec["count"] > 0 else "-"
                    unapproved.append((vcode, info["vchno"], info["date"], info["party"], info["creator"], prev_amt, info["amount"], db_rec["count"], "Unapproved"))
                elif abs(db_rec["amount"] - info["amount"]) > 0.01:
                    unapproved.append((vcode, info["vchno"], info["date"], info["party"], info["creator"], db_rec["amount"], info["amount"], db_rec["count"], "Amount Changed"))
        
        unapproved.reverse()
        
        # Beep notification logic
        current_unapp_count = len(unapproved)
        current_time = time.time()
        should_beep = False
        
        if current_unapp_count > prev_unapproved_count:
            should_beep = True
        elif current_unapp_count > 0 and current_time - last_beep_time >= 60:
            should_beep = True
            
        if should_beep:
            try:
                winsound.PlaySound("SystemAsterisk", winsound.SND_ALIAS | winsound.SND_ASYNC)
            except Exception:
                pass
            last_beep_time = current_time
            
        prev_unapproved_count = current_unapp_count
        
        return jsonify({"success": True, "unapproved": unapproved, "approved": approved})
    except Exception as e:
        logging.exception("Error in /api/data")
        return jsonify({"success": False, "error": str(e)})

@app.route('/api/approve', methods=['POST'])
def api_approve():
    data = request.json
    vcodes = data.get('vcodes', [])
    if not vcodes:
        return jsonify({"success": False, "error": "No vouchers provided"})
        
    try:
        conn = sqlite3.connect(DB_PATH, timeout=5.0)
        c = conn.cursor()
        now = datetime.datetime.now().isoformat()
        
        with conn:
            for vcode in vcodes:
                info = vouchers_cache.get(vcode)
                if not info:
                    continue # Should not happen unless UI is out of sync
                
                vchno = info['vchno']
                new_amt = info['amount']
                
                c.execute("SELECT approval_count FROM approvals WHERE vchcode=?", (vcode,))
                row = c.fetchone()
                
                if row:
                    new_count = (row[0] or 0) + 1
                    c.execute('''
                        UPDATE approvals SET amount=?, status=?, approved_at=?, previous_amount=amount, approval_count=?
                        WHERE vchcode=?
                    ''', (new_amt, "APPROVED", now, new_count, vcode))
                else:
                    c.execute('''
                        INSERT INTO approvals (vchcode, vchno, amount, status, approved_at, previous_amount, approval_count) 
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    ''', (vcode, vchno, new_amt, "APPROVED", now, 0, 1))
        
        return jsonify({"success": True})
    except Exception as e:
        logging.error(f"Approve Error: {e}")
        return jsonify({"success": False, "error": str(e)})

@app.route('/api/cancel', methods=['POST'])
def api_cancel():
    data = request.json
    vcodes = data.get('vcodes', [])
    if not vcodes:
        return jsonify({"success": False, "error": "No vouchers provided"})
        
    try:
        conn = sqlite3.connect(DB_PATH, timeout=5.0)
        c = conn.cursor()
        
        with conn:
            # We must map to tuple of tuples for executemany
            vcode_tuples = [(v,) for v in vcodes]
            c.executemany("UPDATE approvals SET status='UNAPPROVED' WHERE vchcode=?", vcode_tuples)
            
        return jsonify({"success": True})
    except Exception as e:
        logging.error(f"Cancel Error: {e}")
        return jsonify({"success": False, "error": str(e)})

def run_server():
    # Run flask in a background thread so webview can run in main thread
    app.run(host='127.0.0.1', port=5042, debug=False, use_reloader=False)

if __name__ == '__main__':
    init_db()
    threading.Thread(target=init_bfe, daemon=True).start()
    
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    
    # Wait for server to start
    time.sleep(1)
    
    ICON_PATH = os.path.join(PROJECT_DIR, "icon.ico")
    if not os.path.exists(ICON_PATH):
        ICON_PATH = "" # Fallback if missing
    webview.create_window('🌟 Busy Voucher Approval', 'http://127.0.0.1:5042', width=420, height=700, background_color='#0f172a', on_top=True, resizable=False)
    # Note: pywebview icon requires setting sys.argv or modifying manifest on Windows, 
    # but the standalone .exe will have the icon which covers the taskbar and file icon!
    webview.start()
