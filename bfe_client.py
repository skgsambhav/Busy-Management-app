"""
BFE Client - Connects Flask (64-bit) to the BFE bridge (32-bit subprocess).
This module manages the subprocess that runs bfe_bridge.py in 32-bit Python.
"""

import subprocess
import json
import threading
import os
import sys

PYTHON32 = r"C:\Python32\python.exe"  # 32-bit Python
BRIDGE_SCRIPT = os.path.join(os.path.dirname(__file__), "bridge", "dispatcher.py")

_bridge_proc = None
_lock = threading.Lock()


def _get_bridge():
    """Get or start the BFE bridge subprocess."""
    global _bridge_proc
    if _bridge_proc is None or _bridge_proc.poll() is not None:
        _bridge_proc = subprocess.Popen(
            [PYTHON32, BRIDGE_SCRIPT],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,  # Line-buffered
        )
        # Read the init message
        init_line = _bridge_proc.stdout.readline()
        init_data = json.loads(init_line)
        if init_data.get("status") != "ready":
            raise RuntimeError(f"BFE bridge failed to start: {init_data.get('message')}")
    return _bridge_proc


def _send_command(cmd_dict):
    """Send command to bridge and get response."""
    with _lock:
        proc = _get_bridge()
        proc.stdin.write(json.dumps(cmd_dict) + "\n")
        proc.stdin.flush()
        response_line = proc.stdout.readline()
        if not response_line:
            raise RuntimeError("BFE bridge process died unexpectedly")
        result = json.loads(response_line)
        if "error" in result:
            raise RuntimeError(f"BFE Error: {result['error']}\n{result.get('trace','')}")
        return result


# -----------------------------------------------------------------------
# Public API
# -----------------------------------------------------------------------

def get_parties():
    """Get all 483 Sundry Debtor parties."""
    return _send_command({"cmd": "get_parties"})["data"]

def get_suppliers():
    """Get all Sundry Creditors parties."""
    return _send_command({"cmd": "get_suppliers"})["data"]


def get_company_info():
    """Get company info from db.bds."""
    return _send_command({"cmd": "get_company_info"})["data"]


def get_cash_bank_accounts():
    """Get Cash and Bank accounts."""
    return _send_command({"cmd": "get_cash_bank"})["data"]


def get_outstanding_bills(party_code: int):
    """Get outstanding bills for a party."""
    return _send_command({"cmd": "get_outstanding_bills", "party_code": party_code})["data"]


def get_party_balance(party_code: int):
    """Get current balance for a party."""
    return _send_command({"cmd": "get_party_balance", "party_code": party_code})


def get_ledger(party_code: int):
    """Get full chronological ledger for a party."""
    return _send_command({"cmd": "get_ledger", "party_code": party_code})["data"]


def get_trial_balance():
    """Get trial balance for all Debtors and Creditors."""
    return _send_command({"cmd": "get_trial_balance"})["data"]

def get_point_ledger_summary():
    """Get point ledger summary for all contacts."""
    return _send_command({"cmd": "get_point_ledger_summary"})["data"]

def get_point_ledger(party_code: int):
    """Get point ledger transactions for a specific contact."""
    return _send_command({"cmd": "get_point_ledger", "party_code": party_code})["data"]

def get_point_analytics():
    """Get full analytics data for points ledger."""
    return _send_command({"cmd": "get_point_analytics"})["data"]


def get_daybook(date_str: str = None):
    """Get Day Book transactions for a date."""
    return _send_command({"cmd": "get_daybook", "date": date_str})["data"]


def get_sales_vouchers(date_str: str = None):
    """Get Sales Vouchers for a date."""
    return _send_command({"cmd": "get_sales_vouchers", "date": date_str})["data"]


def get_sales_voucher_details(vcode: int):
    """Get full details and line items for a Sales Voucher."""
    return _send_command({"cmd": "get_sales_voucher_details", "vcode": vcode})


def find_sales_voucher(vch_no: str = None, phone: str = None, date_str: str = None):
    """Search for a sales voucher by voucher number or party phone number."""
    return _send_command({"cmd": "find_sales_voucher", "vch_no": vch_no, "phone": phone, "date_str": date_str})["data"]


def find_voucher(vch_no: str = None, phone: str = None, date_str: str = None, hint: str = None):
    """Search for any voucher (Sales, Receipt, Payment) in Tran1."""
    return _send_command({"cmd": "find_voucher", "vch_no": vch_no, "phone": phone, "date_str": date_str, "hint": hint})["data"]




def get_recent_receipts(limit: int = 20):
    """Get recent receipt vouchers."""
    return _send_command({"cmd": "get_recent_receipts", "limit": limit})["data"]


def create_receipt(party_code: int, cash_bank_code: int, amount: float,
                   date_str: str, narration: str = "", bill_adjustments=None):
    return _send_command({
        "cmd": "create_receipt",
        "party_code": party_code,
        "cash_bank_code": cash_bank_code,
        "amount": amount,
        "date": date_str,
        "narration": narration,
        "bill_adjustments": bill_adjustments or []
    })

def create_sales_voucher(date_str: str, customer_code: int, items: list, total_amount: float, narration: str = "", bill_adjustments: list = None, stpt_name: str = "L/GST-Exempt"):
    return _send_command({
        "cmd": "create_sales_voucher",
        "date_str": date_str,
        "customer_code": customer_code,
        "items": items,
        "total_amount": total_amount,
        "narration": narration,
        "bill_adjustments": bill_adjustments or [],
        "stpt_name": stpt_name
    })

def create_purchase_voucher(date_str: str, supplier_code: int, items: list, total_amount: float, narration: str = "", bill_adjustments: list = None, stpt_name: str = "L/GST-Exempt"):
    return _send_command({
        "cmd": "create_purchase_voucher",
        "date_str": date_str,
        "supplier_code": supplier_code,
        "items": items,
        "total_amount": total_amount,
        "narration": narration,
        "bill_adjustments": bill_adjustments or [],
        "stpt_name": stpt_name
    })

def create_gst_purchase_voucher(date_str: str, supplier_code: int, items: list, total_amount: float, narration: str = "", bill_adjustments: list = None, stpt_name: str = "L/GST-ItemWise", bill_no: str = ""):
    return _send_command({
        "cmd": "create_gst_purchase_voucher",
        "date_str": date_str,
        "supplier_code": supplier_code,
        "items": items,
        "total_amount": total_amount,
        "narration": narration,
        "bill_adjustments": bill_adjustments or [],
        "stpt_name": stpt_name,
        "bill_no": bill_no
    })


def get_items():
    """Get all Stock Items with pricing."""
    return _send_command({"cmd": "get_items"})["data"]

def update_master_namesl(master_code: int, name_sl: str):
    """Update the Hindi (Second Language) name for any Master."""
    return _send_command({"cmd": "update_master_namesl", "master_code": master_code, "name_sl": name_sl})


def get_duplicate_receipts(days_gap: int = 3, days_limit: int = 0):
    """Detect double entries for receipts."""
    return _send_command({"cmd": "get_duplicate_receipts", "days_gap": days_gap, "days_limit": days_limit})["data"]

def get_sales_item_duplicates(days: int = 0):
    """Detect duplicate items within the same sales voucher."""
    return _send_command({"cmd": "get_sales_item_duplicates", "days": days})["data"]

def get_cross_voucher_duplicates(months_back: int = 0, days: int = 0):
    """Detect potential cross-voucher duplicates on the same day."""
    return _send_command({"cmd": "get_cross_voucher_duplicates", "months_back": months_back, "days": days})

def get_sales_qty_amt_discrepancies(days: int = 0):
    """Detect sales voucher line items with Qty present but Amt missing, or vice versa."""
    return _send_command({"cmd": "get_sales_qty_amt_discrepancies", "days": days})["data"]

def get_party_vch_100_cash(days: int = 0):
    """Detect sales vouchers where party is not Cash, but the settlement is 100% cash adjusted."""
    return _send_command({"cmd": "get_party_vch_100_cash", "days": days})["data"]


def get_performance_metrics(from_date: str = None, to_date: str = None):
    """Get aggregated daily sales and receipts between dates."""
    return _send_command({"cmd": "get_performance_metrics", "from_date": from_date, "to_date": to_date})["data"]

def get_item_sales_analysis(from_date: str = None, to_date: str = None):
    """Get item-wise sales analysis between dates."""
    return _send_command({"cmd": "get_item_sales_analysis", "from_date": from_date, "to_date": to_date})["data"]

def get_user_analytics(from_date: str = None, to_date: str = None):
    """Get user performance metrics between dates."""
    return _send_command({"cmd": "get_user_analytics", "from_date": from_date, "to_date": to_date})["data"]

def get_employee_analytics(from_date: str = None, to_date: str = None):
    """Get employee (billed/packed) performance metrics between dates."""
    return _send_command({"cmd": "get_employee_analytics", "from_date": from_date, "to_date": to_date})["data"]

def get_commission_analytics(from_date: str = None, to_date: str = None):
    """Get employee commission tracking data."""
    return _send_command({"cmd": "get_commission_analytics", "from_date": from_date, "to_date": to_date})["data"]

def get_user_vouchers(username: str, from_date: str = None, to_date: str = None):
    """Get list of vouchers created by user between dates."""
    return _send_command({"cmd": "get_user_vouchers", "username": username, "from_date": from_date, "to_date": to_date})["data"]

def get_receipt_voucher_details(vcode: int):
    """Get line-item and reference details for a single Receipt Voucher."""
    return _send_command({"cmd": "get_receipt_voucher_details", "vcode": vcode})

def update_item_prices(item_code: int, sale_price: float, purc_price: float, mrp: float, price_a: float = 0, price_b: float = 0, price_c: float = 0, name_sl: str = None, desc1: str = None, desc2: str = None, desc3: str = None, desc4: str = None):
    """Update item prices directly via ADODB."""
    return _send_command({
        "cmd": "update_item_prices",
        "item_code": item_code,
        "sale_price": sale_price,
        "purc_price": purc_price,
        "mrp": mrp,
        "price_a": price_a,
        "price_b": price_b,
        "price_c": price_c,
        "name_sl": name_sl,
        "desc1": desc1,
        "desc2": desc2,
        "desc3": desc3,
        "desc4": desc4
    })



def load_whatsapp_settings():
    """Load WhatsApp configuration settings."""
    return _send_command({"cmd": "load_whatsapp_settings"})["data"]

def save_whatsapp_settings(config):
    """Save WhatsApp configuration settings."""
    return _send_command({"cmd": "save_whatsapp_settings", "config": config})

def test_whatsapp_connection(phone, message):
    """Send a test WhatsApp message to check connection."""
    return _send_command({"cmd": "test_whatsapp_connection", "phone": phone, "message": message})

def send_whatsapp_invoice(vcode, language, phone):
    """Send sales invoice details via WhatsApp."""
    return _send_command({"cmd": "send_whatsapp_invoice", "vcode": vcode, "language": language, "phone": phone})

def send_whatsapp_ledger(party_code, phone):
    """Send ledger summary via WhatsApp."""
    return _send_command({"cmd": "send_whatsapp_ledger", "party_code": party_code, "phone": phone})

def send_whatsapp_media(phone, media_url, filename="Invoice.pdf", caption=""):
    """Send media/PDF file via WhatsApp."""
    return _send_command({
        "cmd": "send_whatsapp_media",
        "phone": phone,
        "media_url": media_url,
        "filename": filename,
        "caption": caption
    })

def get_pending_dispatch_bills():
    """Fetch pending dispatch sales vouchers."""
    return _send_command({"cmd": "get_pending_dispatch_bills"})["data"]

def mark_bill_completed(vno: str):
    """Mark a sales voucher as completed/dispatched."""
    return _send_command({"cmd": "gm_mark_completed", "vno": vno})["data"]

def shutdown():
    """Shutdown the BFE bridge."""
    global _bridge_proc
    if _bridge_proc and _bridge_proc.poll() is None:
        try:
            _bridge_proc.stdin.write(json.dumps({"cmd": "exit"}) + "\n")
            _bridge_proc.stdin.flush()
            _bridge_proc.wait(timeout=5)
        except Exception:
            _bridge_proc.kill()
        _bridge_proc = None
