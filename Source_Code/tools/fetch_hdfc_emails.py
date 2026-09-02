import imaplib
import email
import re
import json
import sqlite3
import os
import sys
from datetime import datetime, timedelta

CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "hdfc_config.json")
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "hdfc_transactions.db")

def load_config():
    if not os.path.exists(CONFIG_PATH):
        return {"email": "", "app_password": ""}
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)

def clean_text(text):
    if text:
        return text.strip().replace('\r', '').replace('\n', ' ')
    return ""

def fetch_and_sync_emails(days=2):
    config = load_config()
    username = config.get("email")
    password = config.get("app_password")

    if not username or not password:
        return {"success": False, "error": "Email credentials not configured. Please save them in Settings."}

    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(username, password)
        mail.select("inbox")
        
        # Superfast filtering: Only search emails since N days ago (default 2 days for current day + yesterday)
        since_date = (datetime.now() - timedelta(days=days)).strftime("%d-%b-%Y")
        search_query = f'(SINCE "{since_date}" FROM "alerts@hdfcbank.bank.in" SUBJECT "Account update")'
        
        status, messages = mail.search(None, search_query)
        if status != "OK" or not messages[0]:
            # Fallback to general search if SINCE query returns empty/fails
            status, messages = mail.search(None, '(FROM "alerts@hdfcbank.bank.in" SUBJECT "Account update")')
            
        if status != "OK" or not messages[0]:
            mail.logout()
            return {"success": True, "message": "No HDFC alert emails found.", "synced": 0}

        email_ids = messages[0].split()
        if not email_ids:
            mail.logout()
            return {"success": True, "message": "No new HDFC alert emails found.", "synced": 0}

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        synced_count = 0
        consecutive_existing = 0

        # Process starting from NEWEST to OLDEST (reversed)
        for e_id in reversed(email_ids):
            uid_str = e_id.decode('utf-8')
            
            # Check if this email is already synced
            cursor.execute("SELECT 1 FROM transactions WHERE email_uid = ?", (uid_str,))
            if cursor.fetchone():
                consecutive_existing += 1
                # If 5 consecutive newest emails are already in DB, stop checking older ones!
                if consecutive_existing >= 5:
                    break
                continue

            consecutive_existing = 0

            # Fetch body text (BODY.PEEK[]) - faster & doesn't mark read
            status, msg_data = mail.fetch(e_id, '(BODY.PEEK[])')
            if status != "OK":
                continue

            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])
                    body = ""

                    if msg.is_multipart():
                        for part in msg.walk():
                            if part.get_content_type() in ["text/plain", "text/html"]:
                                try:
                                    raw = part.get_payload(decode=True).decode(errors='ignore')
                                    if part.get_content_type() == "text/html":
                                        raw = re.sub(r'<[^>]+>', ' ', raw)
                                    body += raw + " "
                                except:
                                    pass
                    else:
                        try:
                            raw = msg.get_payload(decode=True).decode(errors='ignore')
                            if msg.get_content_type() == "text/html":
                                raw = re.sub(r'<[^>]+>', ' ', raw)
                            body += raw
                        except:
                            pass

                    # Parse body
                    amt_match = re.search(r'Rs\.([\d\.]+)\s+has been successfully credited', body)
                    date_match = re.search(r'Date:\s*([\d\-]+)', body)
                    sender_match = re.search(r'Sender:\s*(.*?)\s*\(VPA:\s*(.*?)\)', body)
                    ref_match = re.search(r'UPI Reference No\.:\s*(\d+)', body)

                    if amt_match and date_match and sender_match and ref_match:
                        amt = float(amt_match.group(1))
                        raw_date = date_match.group(1).strip()
                        try:
                            dt_obj = datetime.strptime(raw_date, "%d-%m-%y")
                            db_date = dt_obj.strftime("%Y-%m-%d")
                        except:
                            db_date = raw_date

                        sender_name = clean_text(sender_match.group(1))
                        vpa = clean_text(sender_match.group(2))
                        upi_ref = clean_text(ref_match.group(1))

                        try:
                            cursor.execute('''
                                INSERT INTO transactions (date, amount, sender_name, sender_vpa, upi_ref_no, email_uid)
                                VALUES (?, ?, ?, ?, ?, ?)
                            ''', (db_date, amt, sender_name, vpa, upi_ref, uid_str))
                            synced_count += 1
                        except sqlite3.IntegrityError:
                            pass

        conn.commit()
        conn.close()
        try:
            mail.logout()
        except:
            pass

        return {"success": True, "message": f"Successfully synced {synced_count} new transactions.", "synced": synced_count}

    except Exception as e:
        return {"success": False, "error": str(e)}

if __name__ == "__main__":
    days = 2
    if len(sys.argv) > 1:
        try:
            days = int(sys.argv[1])
        except:
            pass
    res = fetch_and_sync_emails(days=days)
    print(json.dumps(res))
