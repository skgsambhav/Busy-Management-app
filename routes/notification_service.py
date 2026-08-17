import sqlite3
import os
import threading
import time
import datetime
import random
from bridge.whatsapp import send_whatsapp_message
from bfe_client import get_trial_balance
from bridge.ledger import get_outstanding_bills

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "notifications.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS notification_batches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_date TEXT NOT NULL,
            week_key TEXT,
            week_start TEXT NOT NULL,
            week_end TEXT NOT NULL,
            total_customers INTEGER DEFAULT 0,
            sent_count INTEGER DEFAULT 0,
            failed_count INTEGER DEFAULT 0,
            pending_count INTEGER DEFAULT 0,
            status TEXT DEFAULT 'running',
            created_at TEXT NOT NULL,
            completed_at TEXT
        );

        CREATE TABLE IF NOT EXISTS notification_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id INTEGER NOT NULL,
            customer_code INTEGER NOT NULL,
            customer_name TEXT NOT NULL,
            phone TEXT,
            balance_amount REAL DEFAULT 0,
            message_text TEXT,
            status TEXT DEFAULT 'pending',
            error_message TEXT,
            sent_at TEXT,
            retry_count INTEGER DEFAULT 0,
            week_key TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (batch_id) REFERENCES notification_batches(id)
        );

        CREATE TABLE IF NOT EXISTS notification_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
    """)
    
    # Default settings
    settings = {
        "enabled": "0",
        "daily_limit": "150",
        "min_balance": "100",
    }
    
    for k, v in settings.items():
        c.execute("INSERT OR IGNORE INTO notification_settings (key, value) VALUES (?, ?)", (k, v))
        
    conn.commit()
    conn.close()


def build_balance_message(customer_name, balance_amount, pending_bills=None):
    """Build pending balance WhatsApp message - clean mobile-friendly format."""
    
    msg = f"*\U0001f514 \u0938\u093e\u092a\u094d\u0924\u093e\u0939\u093f\u0915 \u092c\u0915\u093e\u092f\u093e \u0938\u0942\u091a\u0928\u093e*\n"
    msg += f"━━━━━━━━━━━━━━━━━━\n"
    msg += f"*AC : {customer_name}*\n"
    msg += f"━━━━━━━━━━━━━━━━━━\n\n"

    # Pending bills section
    if pending_bills and len(pending_bills) > 0:
        msg += f"\U0001f4cb *\u092a\u0947\u0902\u0921\u093f\u0902\u0917 \u092c\u093f\u0932 (Pending Bills)*\n\n"
        total_pending = 0
        for b in pending_bills:
            b_amt = b.get('balance', 0)
            total_pending += b_amt
            dt_str = b.get('date', '')
            if len(dt_str) >= 10 and '/' in dt_str:
                dt_str = dt_str[:5]  # DD/MM only
            msg += f"\U0001f538 *{b.get('bill_no', '')}* ({dt_str})  \u25b6  \u20b9{b_amt:,.2f}\n"
        msg += f"\n\U0001f4b0 *\u0915\u0941\u0932 \u092a\u0947\u0902\u0921\u093f\u0902\u0917 (Pending) : \u20b9{total_pending:,.2f}*\n"
        msg += f"\U0001f4b0 *\u0915\u0941\u0932 \u092c\u0915\u093e\u092f\u093e (Net Balance) : \u20b9{abs(balance_amount):,.2f}*\n"
    else:
        msg += f"\U0001f4b0 *\u0915\u0941\u0932 \u092c\u0915\u093e\u092f\u093e : \u20b9{abs(balance_amount):,.2f}*\n"

    msg += f"\n━━━━━━━━━━━━━━━━━━\n"
    msg += f"*GOPAL MARKETING*\n"
    msg += f"GREEK PARK , AMBIKAPUR\n"
    msg += f"\U0001f4de 9977414177, 9406040611"
    return msg


class NotificationService:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(NotificationService, cls).__new__(cls)
            cls._instance.is_running = False
            cls._instance.current_batch_id = None
            cls._instance.stop_requested = False
            cls._instance.thread = None
            init_db()
        return cls._instance

    def get_settings(self):
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT key, value FROM notification_settings")
        settings = {row['key']: row['value'] for row in c.fetchall()}
        conn.close()
        return settings

    def save_settings(self, settings):
        conn = get_db()
        c = conn.cursor()
        for k, v in settings.items():
            c.execute("INSERT OR REPLACE INTO notification_settings (key, value) VALUES (?, ?)", (k, str(v)))
        conn.commit()
        conn.close()

    def get_iso_week_key(self, date_obj):
        iso_year, iso_week, _ = date_obj.isocalendar()
        return f"{iso_year}-W{iso_week:02d}"
        
    def get_week_range(self, date_obj):
        start = date_obj - datetime.timedelta(days=date_obj.weekday())
        end = start + datetime.timedelta(days=6)
        return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")

    def get_eligible_customers(self, min_balance):
        """Fetch customers with Dr balance >= min_balance.
        This runs in the MAIN thread (Flask request context) so COM works fine."""
        try:
            balances = get_trial_balance()
            eligible = []
            for b in balances:
                if b['dr_cr'] == 'Dr' and b['amount'] >= min_balance:
                    eligible.append(b)
            return eligible
        except Exception as e:
            print(f"Error fetching eligible customers: {e}")
            return []

    def start_weekly_batch(self):
        if self.is_running:
            return {"success": False, "error": "A batch is already running."}
            
        settings = self.get_settings()
        if settings.get("enabled", "0") == "0":
            return {"success": False, "error": "System is currently disabled."}

        # ---- FETCH ALL DATA IN MAIN THREAD (where COM works) ----
        daily_limit = int(settings.get("daily_limit", "150"))
        min_balance = float(settings.get("min_balance", "100"))
        
        today = datetime.datetime.now()
        week_key = self.get_iso_week_key(today)
        
        eligible = self.get_eligible_customers(min_balance)
        if not eligible:
            return {"success": False, "error": "No eligible customers found with pending balance."}

        # Filter out already-sent this week
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT customer_code FROM notification_logs WHERE week_key = ? AND status IN ('sent', 'delivered')", (week_key,))
        already_sent_codes = {row['customer_code'] for row in c.fetchall()}
        conn.close()
        
        to_send = []
        for cust in eligible:
            if cust['code'] not in already_sent_codes:
                # Fetch pending bills NOW in main thread (COM works here)
                try:
                    bills = get_outstanding_bills(cust['code'])
                except:
                    bills = []
                cust['pending_bills'] = bills
                to_send.append(cust)
                if len(to_send) >= daily_limit:
                    break
        
        if not to_send:
            return {"success": False, "error": "All eligible customers have already been notified this week."}

        # ---- NOW START BACKGROUND THREAD with pre-fetched data ----
        self.stop_requested = False
        self.is_running = True
        
        self.thread = threading.Thread(target=self._run_batch, args=(to_send, week_key, today))
        self.thread.daemon = True
        self.thread.start()
        
        return {"success": True, "message": "Batch started in background."}
        
    def stop_batch(self):
        if not self.is_running:
            return {"success": False, "error": "No batch is currently running."}
            
        self.stop_requested = True
        return {"success": True, "message": "Stop requested. It may take a few seconds to halt completely."}

    def _run_batch(self, to_send, week_key, today):
        """Run in background thread. NO COM calls here — only SQLite + HTTP API."""
        try:
            batch_date = today.strftime("%Y-%m-%d")
            week_start, week_end = self.get_week_range(today)

            conn = get_db()
            c = conn.cursor()

            # Create batch
            c.execute("""
                INSERT INTO notification_batches (batch_date, week_key, week_start, week_end, total_customers, pending_count, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (batch_date, week_key, week_start, week_end, len(to_send), len(to_send), datetime.datetime.now().isoformat()))
            self.current_batch_id = c.lastrowid
            conn.commit()

            sent_count = 0
            failed_count = 0
            pending_count = len(to_send)

            for cust in to_send:
                if self.stop_requested:
                    break
                    
                phone = cust.get('mobile', '').strip()

                # Log entry as pending
                c.execute("""
                    INSERT INTO notification_logs (batch_id, customer_code, customer_name, phone, balance_amount, week_key, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (self.current_batch_id, cust['code'], cust['name'], phone, cust['amount'], week_key, datetime.datetime.now().isoformat()))
                log_id = c.lastrowid
                conn.commit()

                if not phone:
                    c.execute("UPDATE notification_logs SET status = 'failed', error_message = 'No phone number found' WHERE id = ?", (log_id,))
                    failed_count += 1
                else:
                    try:
                        # Build message from pre-fetched data (NO COM calls)
                        msg = build_balance_message(cust['name'], cust['amount'], cust.get('pending_bills', []))
                        
                        # Send via WhatsApp API (just HTTP, no COM)
                        res = send_whatsapp_message(phone, msg)
                        
                        if res.get("success"):
                            c.execute("UPDATE notification_logs SET status = 'sent', sent_at = ? WHERE id = ?", (datetime.datetime.now().isoformat(), log_id))
                            sent_count += 1
                        else:
                            c.execute("UPDATE notification_logs SET status = 'failed', error_message = ? WHERE id = ?", (str(res.get("error", "Unknown error")), log_id))
                            failed_count += 1
                    except Exception as e:
                        c.execute("UPDATE notification_logs SET status = 'failed', error_message = ? WHERE id = ?", (str(e), log_id))
                        failed_count += 1
                
                pending_count -= 1
                
                # Update batch progress
                c.execute("""
                    UPDATE notification_batches 
                    SET sent_count = ?, failed_count = ?, pending_count = ?
                    WHERE id = ?
                """, (sent_count, failed_count, pending_count, self.current_batch_id))
                conn.commit()
                
                # Sleep randomly between 60 to 150 seconds (avg ~105s, 150 msgs ≈ 4-5 hours)
                sleep_time = random.randint(60, 150)
                for _ in range(sleep_time):
                    if self.stop_requested:
                        break
                    time.sleep(1)
                
            # Finish batch
            status = 'completed' if not self.stop_requested else 'paused'
            c.execute("UPDATE notification_batches SET status = ?, completed_at = ? WHERE id = ?", (status, datetime.datetime.now().isoformat(), self.current_batch_id))
            conn.commit()
            conn.close()

        except Exception as e:
            print(f"Error in weekly batch: {e}")
            import traceback
            traceback.print_exc()
            if self.current_batch_id:
                try:
                    conn2 = get_db()
                    c2 = conn2.cursor()
                    c2.execute("UPDATE notification_batches SET status = 'error' WHERE id = ?", (self.current_batch_id,))
                    conn2.commit()
                    conn2.close()
                except:
                    pass
        finally:
            self.is_running = False
            self.current_batch_id = None
            self.stop_requested = False
            
    def retry_failed(self, batch_id):
        if self.is_running:
            return {"success": False, "error": "A batch is already running. Wait for it to finish before retrying."}
            
        settings = self.get_settings()
        if settings.get("enabled", "0") == "0":
            return {"success": False, "error": "System is currently disabled."}

        self.stop_requested = False
        self.is_running = True
        
        self.thread = threading.Thread(target=self._run_retry, args=(batch_id,))
        self.thread.daemon = True
        self.thread.start()
        
        return {"success": True, "message": "Retry started in background."}
        
    def _run_retry(self, batch_id):
        """Retry failed messages. NO COM calls — rebuilds message from stored data."""
        try:
            conn = get_db()
            c = conn.cursor()
            
            c.execute("SELECT id, customer_code, customer_name, phone, balance_amount FROM notification_logs WHERE batch_id = ? AND status = 'failed'", (batch_id,))
            failed_logs = [dict(row) for row in c.fetchall()]
            
            if not failed_logs:
                self.is_running = False
                return
                
            c.execute("UPDATE notification_batches SET status = 'retrying' WHERE id = ?", (batch_id,))
            conn.commit()

            c.execute("SELECT sent_count, failed_count, pending_count FROM notification_batches WHERE id = ?", (batch_id,))
            b_row = c.fetchone()
            sent_count = b_row['sent_count']
            failed_count = b_row['failed_count']

            for log in failed_logs:
                if self.stop_requested:
                    break
                    
                log_id = log['id']
                phone = log['phone']
                
                # Update status to retrying
                c.execute("UPDATE notification_logs SET status = 'retrying', retry_count = retry_count + 1 WHERE id = ?", (log_id,))
                conn.commit()
                
                if not phone:
                    c.execute("UPDATE notification_logs SET status = 'failed', error_message = 'No phone number found' WHERE id = ?", (log_id,))
                else:
                    try:
                        msg = build_balance_message(log['customer_name'], log['balance_amount'])
                        res = send_whatsapp_message(phone, msg)
                        
                        if res.get("success"):
                            c.execute("UPDATE notification_logs SET status = 'sent', sent_at = ? WHERE id = ?", (datetime.datetime.now().isoformat(), log_id))
                            sent_count += 1
                            failed_count -= 1
                        else:
                            c.execute("UPDATE notification_logs SET status = 'failed', error_message = ? WHERE id = ?", (str(res.get("error", "Unknown error")), log_id))
                    except Exception as e:
                        c.execute("UPDATE notification_logs SET status = 'failed', error_message = ? WHERE id = ?", (str(e), log_id))
                
                # Update batch progress
                c.execute("""
                    UPDATE notification_batches 
                    SET sent_count = ?, failed_count = ?
                    WHERE id = ?
                """, (sent_count, failed_count, batch_id))
                conn.commit()
                
                # Sleep randomly between 60 to 150 seconds
                sleep_time = random.randint(60, 150)
                for _ in range(sleep_time):
                    if self.stop_requested:
                        break
                    time.sleep(1)
                
            status = 'completed' if not self.stop_requested else 'paused'
            c.execute("UPDATE notification_batches SET status = ? WHERE id = ?", (status, batch_id))
            conn.commit()
            conn.close()
            
        except Exception as e:
            print(f"Error in retry batch: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self.is_running = False
            self.current_batch_id = None
            self.stop_requested = False

notification_service = NotificationService()
