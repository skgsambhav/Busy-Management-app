import threading
import time
import os
import json
import datetime
from bridge.connection import _get_rs
from bridge.whatsapp import send_whatsapp_message

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_FILE = os.path.join(BASE_DIR, "data", "scrutiny_state.json")
CONFIG_FILE = os.path.join(BASE_DIR, "data", "scrutiny_config.json")
DEFAULT_PHONE = "919752830642" # Default admin WhatsApp number

def load_state():
    data_dir = os.path.join(BASE_DIR, "data")
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def save_state(state):
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=4)
    except Exception as e:
        print(f"Error saving scrutiny state: {e}")

def get_admin_phone():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f).get("admin_phone", DEFAULT_PHONE)
        except:
            pass
    return DEFAULT_PHONE

def run_scrutiny_check():
    """Checks for duplicate items in today's sales vouchers."""
    today = datetime.date.today().strftime("%Y-%m-%d")
    
    # 1. Fast check: Get all sales vouchers for today and their amounts
    sql_fast = f"""
        SELECT VchCode, VchNo, VchAmtBaseCur 
        FROM Tran1 
        WHERE VchType = 9 AND Date = #{today}#
    """
    
    current_vouchers = {}
    try:
        rs = _get_rs(sql_fast)
        while not rs.EOF:
            vcode = int(rs.Fields('VchCode').Value)
            vchno = str(rs.Fields('VchNo').Value or "").strip()
            amt = float(rs.Fields('VchAmtBaseCur').Value or 0)
            current_vouchers[vcode] = {"vchno": vchno, "amount": amt}
            rs.MoveNext()
        rs.Close()
    except Exception as e:
        print(f"Scrutiny Fast Check Error: {e}")
        return

    state = load_state()
    vouchers_to_scan = []
    
    # Check which vouchers are new or modified
    for vcode, info in current_vouchers.items():
        vcode_str = str(vcode)
        saved = state.get(vcode_str)
        if not saved or saved.get("amount") != info["amount"]:
            vouchers_to_scan.append(vcode)
            
    if not vouchers_to_scan:
        return # Nothing to do, zero load!

    # 2. Deep scan: Find duplicates only in the modified vouchers
    vch_in = ",".join(map(str, vouchers_to_scan))
    sql_deep = f"""
        SELECT t2.VchCode, m.Name as ItemName, t2.MasterCode1, t2.D1 as Qty, t2.D2 as Rate, t2.Value3 as Amt, COUNT(*) as DupCount
        FROM Tran2 t2
        INNER JOIN Master1 m ON t2.MasterCode1 = m.Code
        WHERE t2.VchCode IN ({vch_in}) AND t2.RecType = 2
          AND (t2.D2 <> 0 OR t2.Value3 <> 0)
        GROUP BY t2.VchCode, m.Name, t2.MasterCode1, t2.D1, t2.D2, t2.Value3
        HAVING COUNT(*) > 1
    """
    
    duplicates_found = []
    dup_dict = {}
    try:
        rs = _get_rs(sql_deep)
        while not rs.EOF:
            vcode = int(rs.Fields('VchCode').Value)
            mcode = int(rs.Fields('MasterCode1').Value)
            item_name = str(rs.Fields('ItemName').Value or "")
            qty = float(rs.Fields('Qty').Value or 0)
            rate = float(rs.Fields('Rate').Value or 0)
            dup_count = int(rs.Fields('DupCount').Value or 0)
            
            dup = {
                "vcode": vcode,
                "item_name": item_name,
                "qty": qty,
                "rate": rate,
                "count": dup_count,
                "sr_nos": []
            }
            key = (vcode, mcode, qty, rate)
            dup_dict[key] = dup
            duplicates_found.append(dup)
            rs.MoveNext()
        rs.Close()
        
        if duplicates_found:
            sql_sr = f"SELECT VchCode, MasterCode1, D1, D2, SrNo FROM Tran2 WHERE VchCode IN ({vch_in}) AND RecType = 2"
            rs2 = _get_rs(sql_sr)
            while not rs2.EOF:
                vc = int(rs2.Fields("VchCode").Value)
                mc = int(rs2.Fields("MasterCode1").Value)
                q = float(rs2.Fields("D1").Value or 0)
                r = float(rs2.Fields("D2").Value or 0)
                sr = int(rs2.Fields("SrNo").Value)
                
                key = (vc, mc, q, r)
                if key in dup_dict:
                    dup_dict[key]["sr_nos"].append(sr)
                rs2.MoveNext()
            rs2.Close()
    except Exception as e:
        print(f"Scrutiny Deep Scan Error: {e}")
        return

    admin_phone = get_admin_phone()
    
    # 3. Process duplicates and update state
    # First, update state for all scanned vouchers so we don't scan them again
    for vcode in vouchers_to_scan:
        vcode_str = str(vcode)
        info = current_vouchers[vcode]
        if vcode_str not in state:
            state[vcode_str] = {"amount": info["amount"], "notified_dupes": []}
        else:
            state[vcode_str]["amount"] = info["amount"]
            
    # Send notifications for new duplicates, grouped by bill
    vch_messages = {}
    
    for dup in duplicates_found:
        vcode_str = str(dup["vcode"])
        vchno = current_vouchers[dup["vcode"]]["vchno"]
        dupe_sig = f"{dup['item_name']}_{dup['qty']}_{dup['rate']}"
        
        # If we haven't notified for this specific duplicate in this voucher yet
        if dupe_sig not in state[vcode_str].get("notified_dupes", []):
            if vcode_str not in vch_messages:
                vch_messages[vcode_str] = {
                    "vchno": vchno,
                    "items": [],
                    "sigs": []
                }
                
            sr_nos_str = ", ".join(map(str, sorted(dup["sr_nos"])))
            item_text = (
                f"🔹 *Item:* {dup['item_name']}\n"
                f"   *Qty:* {abs(dup['qty'])}  |  *Rate:* \u20b9{dup['rate']}\n"
                f"   *Lines:* {sr_nos_str}  ({dup['count']} times)"
            )
            vch_messages[vcode_str]["items"].append(item_text)
            vch_messages[vcode_str]["sigs"].append(dupe_sig)
            
    # Send one combined message per voucher
    for vcode_str, data in vch_messages.items():
        items_str = "\n\n".join(data["items"])
        msg = (
            f"🚨 *Duplicate Items Alert!* 🚨\n\n"
            f"*Bill No:* {data['vchno']}\n\n"
            f"{items_str}\n\n"
            f"Please check this bill in Busy!"
        )
        
        try:
            send_whatsapp_message(admin_phone, msg)
            # Mark as notified
            if "notified_dupes" not in state[vcode_str]:
                state[vcode_str]["notified_dupes"] = []
            state[vcode_str]["notified_dupes"].extend(data["sigs"])
            print(f"Sent combined scrutiny alert for {data['vchno']}")
        except Exception as e:
            print(f"Failed to send combined scrutiny alert: {e}")
            
    # 4. Check for duplicate receipts
    try:
        from bridge.analyzer import get_duplicate_receipts
        rcpt_dupes = get_duplicate_receipts(days_gap=3, days_limit=4)
        
        if "notified_receipts" not in state:
            state["notified_receipts"] = []
            
        for dup in rcpt_dupes:
            sig = f"rcpt_{dup['vch1']}_{dup['vch2']}"
            if sig not in state["notified_receipts"]:
                msg = (
                    f"🚨 *Duplicate Receipt Alert!* 🚨\n\n"
                    f"*Party:* {dup['party']}\n"
                    f"*Amount:* \u20b9{dup['amount']}\n\n"
                    f"🔹 *Receipt 1:* {dup['vch1']} ({dup['date1']})\n"
                    f"🔹 *Receipt 2:* {dup['vch2']} ({dup['date2']})\n\n"
                    f"Gap: {dup['days_diff']} Days"
                )
                try:
                    send_whatsapp_message(admin_phone, msg)
                    state["notified_receipts"].append(sig)
                    print(f"Sent receipt scrutiny alert for {dup['vch1']} and {dup['vch2']}")
                except Exception as e:
                    print(f"Failed to send receipt scrutiny alert: {e}")
    except Exception as e:
        print(f"Scrutiny Receipt Check Error: {e}")

    save_state(state)

def scrutiny_scheduler_loop():
    print("Started Background Scrutiny Scheduler...")
    try:
        import pythoncom
        pythoncom.CoInitialize()
    except Exception as e:
        print(f"Failed to CoInitialize in scrutiny thread: {e}")
        
    while True:
        try:
            run_scrutiny_check()
        except Exception as e:
            print(f"Error in scrutiny scheduler loop: {e}")
        time.sleep(60) # Run every 1 minute

def start_scrutiny_scheduler():
    t = threading.Thread(target=scrutiny_scheduler_loop, daemon=True)
    t.start()
