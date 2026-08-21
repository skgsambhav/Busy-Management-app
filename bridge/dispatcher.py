"""
Bridge dispatcher - JSON stdin/stdout command loop (entry point for 32-bit subprocess).
Must be run with 32-bit Python: C:\\Python32\\python.exe bridge/dispatcher.py
"""

import sys
import os
import json
import traceback

# Verify we are 32-bit
import struct
if struct.calcsize("P") * 8 != 32:
    print(json.dumps({"error": f"Must run with 32-bit Python! Current: {struct.calcsize('P')*8}-bit"}))
    sys.exit(1)

# Add parent directory to path so we can import config and bridge modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bridge.connection import initialize_bfe
from bridge.masters import get_parties, get_cash_bank_accounts, get_company_info, update_master_namesl, get_suppliers
from bridge.ledger import get_outstanding_bills, get_party_balance, get_trial_balance, get_ledger
from bridge.receipts import get_recent_receipts, create_receipt, get_receipt_voucher_details
from bridge.sales import get_daybook, get_sales_vouchers, get_sales_voucher_details, create_sales_voucher, find_sales_voucher, find_voucher
from bridge.items import get_items, update_item_prices
from bridge.ng_purchase import create_purchase_voucher
from bridge.gst_purchase import create_gst_purchase_voucher
from bridge.points import get_point_ledger_summary, get_point_ledger, get_point_analytics_data
from bridge.analyzer import get_duplicate_receipts, get_performance_metrics, get_sales_item_duplicates, get_sales_qty_amt_discrepancies, get_cross_voucher_duplicates, get_party_vch_100_cash, get_item_sales_analysis
from bridge.users import get_user_performance_metrics, get_user_vouchers, get_employee_performance_metrics
from bridge.gm import get_pending_dispatch_bills
from bridge.whatsapp import (
    load_whatsapp_config,
    save_whatsapp_config,
    send_whatsapp_message,
    send_whatsapp_invoice,
    send_whatsapp_ledger,
    send_whatsapp_media
)


def main():
    # Initialize BFE on startup
    try:
        initialize_bfe()
        sys.stdout.write(json.dumps({"status": "ready", "message": "BFE initialized for Comp0002"}) + "\n")
        sys.stdout.flush()
    except Exception as e:
        sys.stdout.write(json.dumps({"status": "error", "message": str(e), "trace": traceback.format_exc()}) + "\n")
        sys.stdout.flush()
        sys.exit(1)
    
    # Command loop
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        
        try:
            cmd = json.loads(line)
            action = cmd.get("cmd", "")
            result = {}
            
            if action == "exit":
                break
            elif action == "get_parties":
                result = {"data": get_parties()}
            elif action == "get_suppliers":
                result = {"data": get_suppliers()}
            elif action == "get_company_info":
                result = {"data": get_company_info()}
            elif action == "get_cash_bank":
                result = {"data": get_cash_bank_accounts()}
            elif action == "get_outstanding_bills":
                result = {"data": get_outstanding_bills(int(cmd["party_code"]))}
            elif action == "get_party_balance":
                result = get_party_balance(int(cmd["party_code"]))
            elif action == "get_ledger":
                result = {"data": get_ledger(int(cmd["party_code"]))}
            elif action == "get_trial_balance":
                result = {"data": get_trial_balance()}
            elif action == "get_point_ledger_summary":
                result = {"data": get_point_ledger_summary()}
            elif action == "get_point_ledger":
                result = {"data": get_point_ledger(int(cmd["party_code"]))}
            elif action == "get_point_analytics":
                result = {"data": get_point_analytics_data()}
            elif action == "get_daybook":
                result = {"data": get_daybook(cmd.get("date"))}
            elif action == "get_sales_vouchers":
                result = {"data": get_sales_vouchers(cmd.get("date"))}
            elif action == "get_sales_voucher_details":
                result = get_sales_voucher_details(int(cmd["vcode"]))
            elif action == "find_sales_voucher":
                result = {"data": find_sales_voucher(vch_no=cmd.get("vch_no"), phone=cmd.get("phone"), date_str=cmd.get("date_str"))}
            elif action == "find_voucher":
                result = {"data": find_voucher(vch_no=cmd.get("vch_no"), phone=cmd.get("phone"), date_str=cmd.get("date_str"), hint=cmd.get("hint"))}
            elif action == "get_receipt_voucher_details":
                result = get_receipt_voucher_details(int(cmd["vcode"]))
            elif action == "get_recent_receipts":
                result = {"data": get_recent_receipts(int(cmd.get("limit", 20)))}
            elif action == "create_receipt":
                result = create_receipt(
                    party_code=int(cmd["party_code"]),
                    cash_bank_code=int(cmd["cash_bank_code"]),
                    amount=float(cmd["amount"]),
                    date_str=str(cmd["date"]),
                    narration=str(cmd.get("narration", "")),
                    bill_adjustments=cmd.get("bill_adjustments", None)
                )
            elif action == "create_sales_voucher":
                result = create_sales_voucher(
                    date_str=str(cmd["date_str"]),
                    customer_code=int(cmd["customer_code"]),
                    items=cmd["items"],
                    total_amount=float(cmd["total_amount"]),
                    narration=str(cmd.get("narration", "")),
                    bill_adjustments=cmd.get("bill_adjustments", []),
                    stpt_name=str(cmd.get("stpt_name", "L/GST-Exempt"))
                )
            elif action == "create_purchase_voucher":
                result = create_purchase_voucher(
                    date_str=str(cmd["date_str"]),
                    supplier_code=int(cmd["supplier_code"]),
                    items=cmd["items"],
                    total_amount=float(cmd["total_amount"]),
                    narration=str(cmd.get("narration", "")),
                    bill_adjustments=cmd.get("bill_adjustments", []),
                    stpt_name=str(cmd.get("stpt_name", "L/GST-Exempt"))
                )
            elif action == "create_gst_purchase_voucher":
                result = create_gst_purchase_voucher(
                    date_str=str(cmd["date_str"]),
                    supplier_code=int(cmd["supplier_code"]),
                    items=cmd["items"],
                    total_amount=float(cmd["total_amount"]),
                    narration=str(cmd.get("narration", "")),
                    bill_adjustments=cmd.get("bill_adjustments", []),
                    stpt_name=str(cmd.get("stpt_name", "L/GST-ItemWise"))
                )
            elif action == "get_items":
                result = {"data": get_items()}
            elif action == "update_item_prices":
                result = update_item_prices(
                    item_code=int(cmd["item_code"]),
                    sale_price=float(cmd["sale_price"]),
                    purc_price=float(cmd["purc_price"]),
                    mrp=float(cmd["mrp"]),
                    price_a=float(cmd.get("price_a", 0)),
                    price_b=float(cmd.get("price_b", 0)),
                    price_c=float(cmd.get("price_c", 0)),
                    name_sl=cmd.get("name_sl"),
                    desc1=cmd.get("desc1"),
                    desc2=cmd.get("desc2"),
                    desc3=cmd.get("desc3"),
                    desc4=cmd.get("desc4")
                )
            elif action == "update_master_namesl":
                result = update_master_namesl(int(cmd["master_code"]), cmd["name_sl"])
            elif action == "get_duplicate_receipts":
                result = {"data": get_duplicate_receipts(int(cmd.get("days_gap", 3)), int(cmd.get("days_limit", 0)))}
            elif action == "get_sales_item_duplicates":
                result = {"data": get_sales_item_duplicates(int(cmd.get("days", 0)))}
            elif action == "get_sales_qty_amt_discrepancies":
                result = {"data": get_sales_qty_amt_discrepancies(int(cmd.get("days", 0)))}
            elif action == "get_cross_voucher_duplicates":
                result = get_cross_voucher_duplicates(int(cmd.get("months_back", 0)), int(cmd.get("days", 0)))
            elif action == "get_party_vch_100_cash":
                result = {"data": get_party_vch_100_cash(int(cmd.get("days", 0)))}
            elif action == "get_max_vchcode":
                from bridge.connection import _get_rs
                rs = _get_rs("SELECT MAX(VchCode) AS MaxVC FROM Tran1")
                val = 0
                if not rs.EOF:
                    raw = rs.Fields("MaxVC").Value
                    val = int(raw) if raw is not None else 0
                rs.Close()
                result = {"data": val}
            elif action == "get_new_vcodes":
                from bridge.connection import _get_rs
                from_vc = int(cmd.get("from_vcode", 0))
                to_vc   = int(cmd.get("to_vcode", 0))
                sql = f"""SELECT VchCode, VchType, VchNo, Date FROM Tran1
                          WHERE VchCode > {from_vc} AND VchCode <= {to_vc}
                          ORDER BY VchCode ASC"""
                rs2 = _get_rs(sql)
                rows = []
                while not rs2.EOF:
                    dt = rs2.Fields("Date").Value
                    rows.append({
                        "vcode": int(rs2.Fields("VchCode").Value),
                        "vtype": int(rs2.Fields("VchType").Value),
                        "vno":   str(rs2.Fields("VchNo").Value or "").strip(),
                        "date":  str(dt)[:10] if dt else "",
                    })
                    rs2.MoveNext()
                rs2.Close()
                result = {"data": rows}
            elif action == "get_performance_metrics":
                from_date = cmd.get("from_date")
                to_date = cmd.get("to_date")
                result = {"data": get_performance_metrics(from_date, to_date)}
            elif action == "get_item_sales_analysis":
                from_date = cmd.get("from_date")
                to_date = cmd.get("to_date")
                result = {"data": get_item_sales_analysis(from_date, to_date)}
            elif action == "get_user_analytics":
                from_date = cmd.get("from_date")
                to_date = cmd.get("to_date")
                result = {"data": get_user_performance_metrics(from_date, to_date)}
            elif action == "get_employee_analytics":
                from_date = cmd.get("from_date")
                to_date = cmd.get("to_date")
                result = {"data": get_employee_performance_metrics(from_date, to_date)}
            elif action == "get_commission_analytics":
                from_date = cmd.get("from_date")
                to_date = cmd.get("to_date")
                from bridge.users import get_commission_analytics
                result = {"data": get_commission_analytics(from_date, to_date)}
            elif action == "get_user_vouchers":
                username = cmd.get("username")
                from_date = cmd.get("from_date")
                to_date = cmd.get("to_date")
                result = {"data": get_user_vouchers(username, from_date, to_date)}
            elif action == "get_pending_dispatch_bills":
                result = {"data": get_pending_dispatch_bills()}
            elif action == "gm_mark_completed":
                from bridge.gm import mark_bill_completed
                result = {"data": mark_bill_completed(cmd.get("vno"))}
            elif action == "load_whatsapp_settings":
                result = {"data": load_whatsapp_config()}
            elif action == "save_whatsapp_settings":
                result = save_whatsapp_config(cmd.get("config"))
            elif action == "test_whatsapp_connection":
                result = send_whatsapp_message(cmd.get("phone"), cmd.get("message", "Hello from Buswin App!"))
            elif action == "send_whatsapp_invoice":
                result = send_whatsapp_invoice(int(cmd.get("vcode")), cmd.get("language"), cmd.get("phone"))
            elif action == "send_whatsapp_ledger":
                result = send_whatsapp_ledger(int(cmd.get("party_code")), cmd.get("phone"))
            elif action == "send_whatsapp_media":
                result = send_whatsapp_media(
                    cmd.get("phone"),
                    cmd.get("media_url"),
                    cmd.get("filename", "Invoice.pdf"),
                    cmd.get("caption", "")
                )
            else:
                result = {"error": f"Unknown command: {action}"}
            
            sys.stdout.write(json.dumps(result) + "\n")
            sys.stdout.flush()
        
        except Exception as e:
            sys.stdout.write(json.dumps({"error": str(e), "trace": traceback.format_exc()}) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
