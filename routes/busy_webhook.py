"""
routes/busy_webhook.py — Busy 21 Win SMS & PDF Dispatch Webhook
Receives dispatch requests from Busy Win (via SMS Configuration -> BMS PDF / Service Provider Server),
immediately returns 200 OK to prevent Busy from freezing, and processes the dispatch (PDF/HTML upload & WhatsApp message)
asynchronously in a background worker pool.
"""

import os
import re
import json
import logging
import sqlite3
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from flask import Blueprint, request, jsonify, make_response

import bfe_client
from services.r2_store import upload_invoice_html, upload_ledger_html, upload_pdf_bytes
from services.invoice_renderer import render_invoice_html
from services.ledger_renderer import render_ledger_html
from routes.invoices import _build_ledger_whatsapp_msg
from bridge.whatsapp import send_whatsapp_message, send_whatsapp_media, parse_and_clean_phone_numbers

logger = logging.getLogger(__name__)

busy_webhook_bp = Blueprint("busy_webhook", __name__)

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "dispatches.db")

# Thread pool for asynchronous WhatsApp dispatching without blocking Busy UI
executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="busy_dispatch_worker")


def _init_busy_log_db():
    """Ensure busy_dispatches table exists in dispatches.db."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS busy_dispatches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    phone TEXT,
                    vno TEXT,
                    vcode INTEGER,
                    party_name TEXT,
                    amount REAL,
                    html_url TEXT,
                    pdf_url TEXT,
                    message_text TEXT,
                    status TEXT,
                    error_msg TEXT
                )
            """)
            conn.commit()
    except Exception as e:
        logger.error(f"[Busy Webhook] DB init failed: {e}")


_init_busy_log_db()


def _log_dispatch(phone, vno, vcode, party_name, amount, html_url, pdf_url, message_text, status, error_msg=""):
    """Record dispatch event in SQLite for dashboard / audit log."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("""
                INSERT INTO busy_dispatches 
                (timestamp, phone, vno, vcode, party_name, amount, html_url, pdf_url, message_text, status, error_msg)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                phone,
                vno or "",
                vcode or 0,
                party_name or "",
                float(amount or 0),
                html_url or "",
                pdf_url or "",
                message_text or "",
                status,
                error_msg or ""
            ))
            conn.commit()
    except Exception as e:
        logger.error(f"[Busy Webhook] Failed to log dispatch: {e}")


def _find_party_by_phone_or_name(phone: str = "", name_hint: str = ""):
    """Find party dict from Busy database by phone number or party name."""
    try:
        parties = bfe_client.get_parties()
    except Exception as e:
        logger.error(f"[Busy Webhook] Failed to fetch parties: {e}")
        return None
        
    last10 = ""
    if phone:
        digits = ''.join(c for c in str(phone) if c.isdigit())
        if len(digits) >= 10:
            last10 = digits[-10:]
            
    # 1. Try matching by phone
    if last10:
        for p in parties:
            p_mob = ''.join(c for c in str(p.get("mobile", "")) if c.isdigit())
            if last10 in p_mob or p_mob.endswith(last10):
                return p
                
    # 2. Try matching by name hint
    if name_hint:
        clean_hint = name_hint.strip().lower()
        # Exact match
        for p in parties:
            if str(p.get("name", "")).strip().lower() == clean_hint:
                return p
        # Substring match
        for p in parties:
            p_name = str(p.get("name", "")).strip().lower()
            if clean_hint in p_name or p_name in clean_hint:
                return p
                
    return None


def _extract_vch_no_and_hint(text: str, filename: str = ""):
    """
    Extract candidate voucher number, report type hint ('ledger', 'receipt', 'sale', or None),
    and candidate party name.
    Returns (vch_no_candidate, hint, party_name_hint).
    """
    hint = None
    vch_no = ""
    party_name_hint = ""
    
    combined_lower = f"{text or ''} {filename or ''}".lower()
    
    # 1. Check for Ledger / Account Statement
    if any(k in combined_lower for k in ["l e d g e r", "ledger", "account ledger", "statement", "खाता", "खाता विवरण", "बकाया"]):
        hint = "ledger"
    elif any(k in combined_lower for k in ["rcpt", "receipt", "received with thanks", "रसीद", "प्राप्त राशि"]):
        hint = "receipt"
    elif any(k in combined_lower for k in ["sale", "invoice", "बिल"]):
        hint = "sale"
        
    # Extract party name candidate from text if present (e.g. Dear 'OM SHREE VINAYAK - LAKHANPUR')
    if text:
        m = re.search(r"Dear\s+['\"]([^'\"]+)['\"]", text, re.IGNORECASE)
        if m:
            party_name_hint = m.group(1).strip()
        else:
            m2 = re.search(r"Dear\s+([A-Za-z0-9\s\.\-\&\/]+?)(?:,|\s+Please|\s+find|\s+attached|\.|$)", text, re.IGNORECASE)
            if m2:
                party_name_hint = m2.group(1).strip()
        
    # 2. Check filename patterns
    if filename:
        # Pattern: -Rcpt-GMRCPT1262-154023.pdf or -Sale-GM4165-154023.pdf
        m = re.search(r'[-_]?(?:Sale|Purc|Rcpt|Receipt|Pay|Vch|Invoice)[-_]([A-Za-z0-9\/]+)(?:-\d+)?(?:\.pdf|\b)', filename, re.IGNORECASE)
        if m:
            vch_no = m.group(1).strip()
            if "rcpt" in filename.lower() or "receipt" in filename.lower():
                hint = "receipt"
            elif "sale" in filename.lower():
                hint = "sale"
            return vch_no, hint, party_name_hint
            
        # Pattern: GMRCPT1262-154023.pdf or GM4165-154023.pdf
        m = re.search(r'([A-Za-z0-9\/]+)-\d{6}(?:\.pdf|\b)', filename, re.IGNORECASE)
        if m:
            vch_no = m.group(1).strip()
            if vch_no.upper().startswith("GMRCPT") or vch_no.upper().startswith("RCPT"):
                hint = "receipt"
            elif vch_no.upper().startswith("GM"):
                hint = "sale"
            return vch_no, hint, party_name_hint
            
        # Direct GMRCPT or GM voucher in filename
        m = re.search(r'\b(GMRCPT\d+|RCPT\d+|GM\d+)\b', filename, re.IGNORECASE)
        if m:
            vch_no = m.group(1).strip()
            if vch_no.upper().startswith("GMRCPT") or vch_no.upper().startswith("RCPT"):
                hint = "receipt"
            elif vch_no.upper().startswith("GM"):
                hint = "sale"
            return vch_no, hint, party_name_hint

    # 3. Check message text patterns
    if text:
        # Pattern: GMRCPT1262 or RCPT1262
        m = re.search(r'\b(GMRCPT\d+|RCPT\d+)\b', text, re.IGNORECASE)
        if m:
            return m.group(1).strip(), "receipt", party_name_hint
            
        # Pattern: GM4165
        m = re.search(r'\b(GM\d+)\b', text, re.IGNORECASE)
        if m:
            return m.group(1).strip(), "sale", party_name_hint
            
        # Pattern: GM/26-27/001
        m = re.search(r'\b(GM\/[0-9\-]+\/\d+)\b', text, re.IGNORECASE)
        if m:
            return m.group(1).strip(), "sale", party_name_hint
            
        # Pattern: Invoice No: 1234 or Receipt No: 1234
        m = re.search(r'(?:Invoice|Bill|Inv|Receipt|Rcpt|Vch|Voucher)\s*(?:No\.?|#|:)\s*([A-Za-z0-9\/\-]+)', text, re.IGNORECASE)
        if m:
            cand = m.group(1).strip()
            if "receipt" in text.lower() or "rcpt" in text.lower():
                hint = "receipt"
            return cand, hint, party_name_hint

    return vch_no, hint, party_name_hint


def _build_receipt_whatsapp_msg(receipt_data: dict, current_balance: str = "") -> str:
    """Build a compact, clean WhatsApp payment receipt message."""
    vno = receipt_data.get("vno") or receipt_data.get("vchno", "")
    date_str = receipt_data.get("date", "")
    amount = float(receipt_data.get("amount", 0))
    party_name = receipt_data.get("party_name", "Customer")
    mode = receipt_data.get("cash_bank_name", "Cash/Bank")
    adjustments = receipt_data.get("adjustments", [])
    
    msg  = f"🏪 *गोपाल मार्केटिंग (GOPAL MARKETING)*\n"
    msg += f"📍 ग्रीक पार्क, अंबिकापुर | 📞 9977414177\n"
    msg += f"━━━━━━━━━━━━━━━━━━\n"
    msg += f"🧾 *भुगतान रसीद / PAYMENT RECEIPT*\n"
    msg += f"🏢 *{party_name}*\n"
    msg += f"📋 रसीद नं: *{vno}* | 📅 दिनांक: {date_str}\n"
    msg += f"💰 प्राप्त राशि: *₹{amount:,.2f}* ({mode})\n"
    
    if adjustments:
        adj_strs = [f"{a['ref_no']}: ₹{a['amount']:,.2f}" for a in adjustments]
        msg += f"🔹 एडजस्ट बिल: {', '.join(adj_strs)}\n"
        
    if current_balance:
        msg += f"📊 वर्तमान बकाया: *{current_balance}*\n"
        
    msg += f"━━━━━━━━━━━━━━━━━━\n"
    msg += f"🙏 *भुगतान के लिए धन्यवाद!*"
    return msg


def _build_invoice_whatsapp_msg(vno: str, date_str: str, party_name: str,
                                total: float, url: str) -> str:
    """Build a compact, clean WhatsApp text message with invoice link."""
    if str(total).startswith("₹"):
        formatted_total = str(total)
    else:
        try:
            val = float(str(total).replace(",", ""))
            formatted_total = f"₹{val:,.2f}"
        except Exception:
            formatted_total = f"₹{total}"
    
    msg  = f"🏪 *गोपाल मार्केटिंग (GOPAL MARKETING)*\n"
    msg += f"📍 ग्रीक पार्क, अंबिकापुर | 📞 9977414177\n"
    msg += f"━━━━━━━━━━━━━━━━━━\n"
    msg += f"🧾 *सेल्स बिल / SALES INVOICE*\n"
    msg += f"🏢 *{party_name}*\n"
    msg += f"📋 बिल नं: *{vno}* | 📅 दिनांक: {date_str}\n"
    msg += f"💰 कुल राशि: *{formatted_total}*\n"
    msg += f"━━━━━━━━━━━━━━━━━━\n"
    msg += f"📲 *डिजिटल बिल देखें / View & Download:*\n"
    msg += f"👉 {url}\n\n"
    msg += f"💡 _लिंक नीली (Clickable) न हो तो नंबर Save करें या 'Hi' भेजें।_"
    return msg


def _process_dispatch_background(target_phone: str, message_text: str, pdf_bytes: bytes, pdf_filename: str):
    """
    Background worker that runs asynchronously after 200 OK has been returned to Busy.
    Fetches DB voucher details, renders/uploads HTML/PDF, and sends WhatsApp message.
    """
    logger.info(f"[Busy Webhook Async] Processing dispatch for phone={target_phone}, file={pdf_filename}")
    
    # 1. Search for corresponding voucher / report in Busy Database
    vch_no_candidate, hint, party_name_hint = _extract_vch_no_and_hint(message_text, pdf_filename)
    vcode = None
    vtype = None
    found_vno = ""
    
    if hint != "ledger":
        try:
            found_vch = bfe_client.find_voucher(vch_no=vch_no_candidate, phone=target_phone, hint=hint)
            if found_vch and found_vch.get("vcode"):
                vcode = int(found_vch["vcode"])
                vtype = int(found_vch.get("vtype") or 9)
                found_vno = found_vch.get("vno", "")
        except Exception as e:
            logger.warning(f"[Busy Webhook Async] Voucher lookup failed: {e}")

    # 2. Dispatch based on Voucher Type / Report Type
    dispatch_status = "DELIVRD"
    error_detail = ""
    public_html_url = None
    public_pdf_url = None
    vno = found_vno
    party_name = ""
    total_amt = 0.0

    try:
        # ──────── Case L: ACCOUNT LEDGER (Digital Statement) ────────
        if hint == "ledger":
            party = _find_party_by_phone_or_name(target_phone, party_name_hint)
            if party:
                party_code = int(party["code"])
                party_name = party.get("name", party_name_hint or "Customer")
                party_name_hi = party.get("name_hi") or party.get("name_sl") or ""
                
                ledger_data = bfe_client.get_ledger(party_code)
                pending_bills = bfe_client.get_outstanding_bills(party_code)
                try:
                    company_info = bfe_client.get_company_info()
                except Exception:
                    company_info = {}
                    
                html_content = render_ledger_html(
                    party_name=party_name,
                    party_name_hi=party_name_hi,
                    ledger_data=ledger_data,
                    pending_bills=pending_bills,
                    company_info=company_info
                )
                public_html_url = upload_ledger_html(party_code, html_content)
                logger.info(f"[Busy Webhook Async] Generated online ledger HTML for party={party_code}: {public_html_url}")
                
                op_bal = float(ledger_data.get("op_bal", 0))
                transactions = ledger_data.get("transactions", [])
                running = op_bal
                for t in transactions:
                    running += float(t.get("amount", 0))
                    
                dr_cr = "Dr" if running < 0 else "Cr"
                balance_text = f"₹{abs(running):,.2f}"
                total_amt = abs(running)
                vno = "LEDGER"
                
                msg = _build_ledger_whatsapp_msg(party_name, balance_text, dr_cr, public_html_url)
                send_whatsapp_message(target_phone, msg)
                logger.info(f"[Busy Webhook Async] Sent online ledger link for {party_name} to {target_phone} -> {public_html_url}")
            else:
                final_msg = message_text or f"Account Ledger from GOPAL MARKETING."
                send_whatsapp_message(target_phone, final_msg)

        # ──────── Case A: RECEIPT VOUCHER (VchType = 14) ────────
        elif vcode and vtype == 14:
            receipt_data = bfe_client.get_receipt_voucher_details(vcode)
            if "error" not in receipt_data:
                vno = receipt_data.get("vno") or receipt_data.get("vchno", vno)
                party_name = receipt_data.get("party_name", "")
                total_amt = float(receipt_data.get("amount", 0))
                
                # Fetch party balance
                party_code = receipt_data.get("party_code", 0)
                balance_text = ""
                if party_code:
                    try:
                        bal_res = bfe_client.get_party_balance(party_code)
                        if bal_res:
                            bal_val = bal_res.get("amount", 0)
                            dr_cr = bal_res.get("dr_cr", "Dr")
                            balance_text = f"₹{bal_val:,.2f} {dr_cr}"
                    except Exception:
                        pass
                
                msg = _build_receipt_whatsapp_msg(receipt_data, current_balance=balance_text)
                send_whatsapp_message(target_phone, msg)
                logger.info(f"[Busy Webhook Async] Sent Payment Receipt {vno} to {target_phone}")
            else:
                final_msg = message_text or f"Payment received successfully for {vno}."
                send_whatsapp_message(target_phone, final_msg)

        # ──────── Case B: SALES INVOICE (VchType = 9) ────────
        elif vcode and vtype == 9:
            voucher_data = bfe_client.get_sales_voucher_details(vcode)
            if "error" not in voucher_data:
                vno = voucher_data.get("vno", vno)
                party_name = voucher_data.get("party_name", "")
                total_amt = float(voucher_data.get("total_amount", 0))
                
                try:
                    company_info = bfe_client.get_company_info()
                except Exception:
                    company_info = {}
                    
                html_content = render_invoice_html(voucher_data, company_info)
                public_html_url = upload_invoice_html(vcode, html_content)
                logger.info(f"[Busy Webhook Async] Generated online bill HTML for vcode={vcode}: {public_html_url}")
                
                date_str = voucher_data.get("date", "")
                if "-" in date_str and len(date_str) >= 10:
                    p = date_str[:10].split("-")
                    date_str = f"{p[2]}/{p[1]}/{p[0]}"
                    
                msg = _build_invoice_whatsapp_msg(vno, date_str, party_name, total_amt, public_html_url)
                send_whatsapp_message(target_phone, msg)
                logger.info(f"[Busy Webhook Async] Sent online bill link for {vno} to {target_phone} -> {public_html_url}")
            else:
                final_msg = message_text or f"Invoice {vno} from GOPAL MARKETING."
                send_whatsapp_message(target_phone, final_msg)

        # ──────── Case C: Generic SMS / Other Vouchers ────────
        else:
            final_msg = message_text or "Hello, thank you for your business with GOPAL MARKETING."
            send_whatsapp_message(target_phone, final_msg)
            logger.info(f"[Busy Webhook Async] Sent generic message to {target_phone}")

    except Exception as e:
        dispatch_status = "FAILED"
        error_detail = str(e)
        logger.error(f"[Busy Webhook Async] WhatsApp dispatch error: {e}")

    # 4. Record in audit database
    _log_dispatch(
        phone=target_phone,
        vno=vno,
        vcode=vcode,
        party_name=party_name,
        amount=total_amt,
        html_url=public_html_url,
        pdf_url=public_pdf_url,
        message_text=message_text,
        status=dispatch_status,
        error_msg=error_detail
    )


def _parse_params():
    """Extract params from GET query, POST form, JSON, or Files."""
    params = {}
    
    # Query Args
    if request.args:
        for k, v in request.args.items():
            params[k] = v
            
    # Form data
    if request.form:
        for k, v in request.form.items():
            params[k] = v
            
    # JSON body
    if request.is_json:
        try:
            j = request.get_json(silent=True) or {}
            for k, v in j.items():
                params[k] = v
        except:
            pass
            
    return params


@busy_webhook_bp.route("/api/message/busy-send", methods=["GET", "POST"])
@busy_webhook_bp.route("/api/busy/send", methods=["GET", "POST"])
@busy_webhook_bp.route("/api/busy-send", methods=["GET", "POST"])
def handle_busy_send():
    """
    Main webhook receiver for Busy 21 Win.
    Matches Busy SMS configuration parameters:
      - senderId: Sender phone / ID
      - authToken: Auth token / API key
      - receiverId / mobile / to: Recipient mobile number
      - messageText / message / text: Message body
      - Uploaded PDF file in multipart request
    
    Returns HTTP 200 immediately (<10ms) to ensure Busy Win NEVER freezes.
    All background processing (DB lookups, R2 uploads, WhatsApp sending) occurs asynchronously.
    """
    params = _parse_params()
    
    # 1. Recipient phone number
    phone_raw = (
        params.get("receiverId") or
        params.get("receiverid") or
        params.get("mobile") or
        params.get("phone") or
        params.get("to") or
        params.get("MobileNo") or
        params.get("Mobile") or
        params.get("recipient") or
        ""
    )
    
    # 2. Message text
    message_text = (
        params.get("messageText") or
        params.get("messagetext") or
        params.get("message") or
        params.get("msg") or
        params.get("text") or
        params.get("body") or
        params.get("caption") or
        ""
    ).strip()
    
    # 3. Read uploaded files (PDF) into memory before request closes
    pdf_bytes = None
    pdf_filename = ""
    if request.files:
        for file_key in request.files:
            f = request.files[file_key]
            if f and f.filename:
                try:
                    pdf_bytes = f.read()
                    pdf_filename = f.filename
                except Exception as e:
                    logger.warning(f"[Busy Webhook] Failed to read uploaded file: {e}")
                break

    # Validate recipient phone
    phone_list = parse_and_clean_phone_numbers(phone_raw)
    if not phone_list:
        err = f"Invalid or missing recipient phone number: '{phone_raw}'"
        logger.warning(f"[Busy Webhook] {err}")
        _log_dispatch(phone_raw, "", 0, "", 0, "", "", message_text, "FAILED", err)
        return jsonify({
            "success": False,
            "status": "FAILED",
            "error": err
        }), 400

    target_phone = phone_list[0]
    
    # 4. Offload heavy processing to background thread pool (Non-blocking!)
    executor.submit(
        _process_dispatch_background,
        target_phone=target_phone,
        message_text=message_text,
        pdf_bytes=pdf_bytes,
        pdf_filename=pdf_filename
    )

    # 5. INSTANT HTTP 200 OK Response back to Busy Win!
    return jsonify({
        "success": True,
        "status": "DELIVRD",
        "message": "Queued for instant WhatsApp dispatch",
        "phone": target_phone
    }), 200


@busy_webhook_bp.route("/api/busy/dispatches", methods=["GET"])
def get_recent_busy_dispatches():
    """API endpoint to view recent dispatches triggered from Busy Win."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT * FROM busy_dispatches 
                ORDER BY id DESC LIMIT 50
            """).fetchall()
            
            dispatches = [dict(row) for row in rows]
            return jsonify({"success": True, "dispatches": dispatches})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
