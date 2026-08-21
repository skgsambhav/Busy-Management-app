"""
Standalone Scrutiny Runner - always runs under C:\\Python32\\python.exe
Called as a subprocess from the main Flask app so COM (BFE) works correctly.
"""
import sys
import os
import time
import json
import datetime

# Ensure we can find the project root
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(BASE_DIR)
sys.path.insert(0, PROJECT_DIR)

STATE_FILE = os.path.join(PROJECT_DIR, "data", "scrutiny_state.json")
CONFIG_FILE = os.path.join(PROJECT_DIR, "data", "scrutiny_config.json")
DEFAULT_PHONE = "919752830642"
INTERVAL = 30  # seconds

def load_state():
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
        print(f"Error saving state: {e}", flush=True)

def get_admin_phone():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f).get("admin_phone", DEFAULT_PHONE)
        except:
            pass
    return DEFAULT_PHONE

def run_check(bfe_conn, whatsapp_sender):
    today = datetime.date.today().strftime("%Y-%m-%d")

    # -- Step 1: Fast check for today's sales vouchers --
    sql_fast = f"SELECT VchCode, VchNo, VchAmtBaseCur FROM Tran1 WHERE VchType = 9 AND Date = #{today}#"
    current_vouchers = {}
    try:
        rs = bfe_conn(sql_fast)
        while not rs.EOF:
            vcode = int(rs.Fields('VchCode').Value)
            vchno = str(rs.Fields('VchNo').Value or "").strip()
            amt = float(rs.Fields('VchAmtBaseCur').Value or 0)
            current_vouchers[vcode] = {"vchno": vchno, "amount": amt}
            rs.MoveNext()
        rs.Close()
    except Exception as e:
        print(f"Fast check error: {e}", flush=True)
        return

    state = load_state()
    vouchers_to_scan = []
    for vcode, info in current_vouchers.items():
        vcode_str = str(vcode)
        if vcode_str not in state:
            vouchers_to_scan.append(vcode)
        elif state[vcode_str].get("amount") != info["amount"]:
            # Amount changed = bill was edited, clear old notified dupes so all re-send
            state[vcode_str]["notified_dupes"] = []
            vouchers_to_scan.append(vcode)

    # -- Step 2: Deep scan for duplicates --
    if vouchers_to_scan:
        vch_in = ",".join(map(str, vouchers_to_scan))
        sql_deep = f"""
            SELECT t2.VchCode, m.Name as ItemName, t2.MasterCode1, t2.D2 as Rate, 
                   SUM(ABS(t2.D1)) as TotalQty, COUNT(*) as DupCount
            FROM Tran2 t2
            INNER JOIN Master1 m ON t2.MasterCode1 = m.Code
            WHERE t2.VchCode IN ({vch_in}) AND t2.RecType = 2
              AND (t2.D2 <> 0 OR t2.Value3 <> 0)
            GROUP BY t2.VchCode, m.Name, t2.MasterCode1, t2.D2
            HAVING COUNT(*) > 1
        """
        dup_dict = {}
        duplicates_found = []
        try:
            rs = bfe_conn(sql_deep)
            while not rs.EOF:
                vcode = int(rs.Fields('VchCode').Value)
                mcode = int(rs.Fields('MasterCode1').Value)
                item_name = str(rs.Fields('ItemName').Value or "")
                rate = float(rs.Fields('Rate').Value or 0)
                total_qty = float(rs.Fields('TotalQty').Value or 0)
                dup_count = int(rs.Fields('DupCount').Value or 0)
                dup = {"vcode": vcode, "item_name": item_name, "qty": total_qty, "rate": rate, "count": dup_count, "sr_nos": []}
                key = (vcode, mcode, rate)
                dup_dict[key] = dup
                duplicates_found.append(dup)
                rs.MoveNext()
            rs.Close()

            if duplicates_found:
                rs2 = bfe_conn(f"SELECT VchCode, MasterCode1, D1, D2, SrNo FROM Tran2 WHERE VchCode IN ({vch_in}) AND RecType = 2")
                while not rs2.EOF:
                    key = (int(rs2.Fields("VchCode").Value), int(rs2.Fields("MasterCode1").Value),
                           float(rs2.Fields("D2").Value or 0))
                    if key in dup_dict:
                        dup_dict[key]["sr_nos"].append(int(rs2.Fields("SrNo").Value))
                    rs2.MoveNext()
                rs2.Close()
        except Exception as e:
            print(f"Deep scan error: {e}", flush=True)

        # Update state for scanned vouchers
        for vcode in vouchers_to_scan:
            vcode_str = str(vcode)
            if vcode_str not in state:
                state[vcode_str] = {"amount": current_vouchers[vcode]["amount"], "notified_dupes": []}
            else:
                state[vcode_str]["amount"] = current_vouchers[vcode]["amount"]

        # Group duplicates by voucher and send one message per voucher
        admin_phone = get_admin_phone()
        vch_messages = {}
        for dup in duplicates_found:
            vcode_str = str(dup["vcode"])
            vchno = current_vouchers[dup["vcode"]]["vchno"]
            dupe_sig = f"{dup['item_name']}_{dup['rate']}"
            if dupe_sig not in state[vcode_str].get("notified_dupes", []):
                if vcode_str not in vch_messages:
                    vch_messages[vcode_str] = {"vchno": vchno, "items": [], "sigs": []}
                sr_str = ", ".join(map(str, sorted(dup["sr_nos"])))
                vch_messages[vcode_str]["items"].append(
                    f"🔹 *Item:* {dup['item_name']}\n"
                    f"   *Total Qty:* {dup['qty']}  |  *Rate:* \u20b9{dup['rate']}\n"
                    f"   *Lines:* {sr_str}  ({dup['count']} times)"
                )
                vch_messages[vcode_str]["sigs"].append(dupe_sig)

        for vcode_str, data in vch_messages.items():
            msg = (
                f"\U0001f6a8 *Duplicate Items Alert!* \U0001f6a8\n\n"
                f"*Bill No:* {data['vchno']}\n\n"
                + "\n\n".join(data["items"])
                + "\n\nPlease check this bill in Busy!"
            )
            try:
                whatsapp_sender(admin_phone, msg)
                state[vcode_str].setdefault("notified_dupes", []).extend(data["sigs"])
                print(f"Sent combined scrutiny alert for {data['vchno']}", flush=True)
            except Exception as e:
                print(f"Failed to send alert: {e}", flush=True)

    # -- Step 3: Duplicate Receipts --
    try:
        from bridge.analyzer import get_duplicate_receipts
        admin_phone = get_admin_phone()
        rcpt_dupes = get_duplicate_receipts(days_gap=3, days_limit=4)
        if "notified_receipts" not in state:
            state["notified_receipts"] = []
        for dup in rcpt_dupes:
            sig = f"rcpt_{dup['vch1']}_{dup['vch2']}"
            if sig not in state["notified_receipts"]:
                msg = (
                    f"\U0001f6a8 *Duplicate Receipt Alert!* \U0001f6a8\n\n"
                    f"*Party:* {dup['party']}\n"
                    f"*Amount:* \u20b9{dup['amount']}\n\n"
                    f"🔹 *Receipt 1:* {dup['vch1']} ({dup['date1']})\n"
                    f"🔹 *Receipt 2:* {dup['vch2']} ({dup['date2']})\n\n"
                    f"Gap: {dup['days_diff']} Days"
                )
                try:
                    whatsapp_sender(admin_phone, msg)
                    state["notified_receipts"].append(sig)
                    print(f"Sent receipt alert for {dup['vch1']} & {dup['vch2']}", flush=True)
                except Exception as e:
                    print(f"Failed to send receipt alert: {e}", flush=True)
    except Exception as e:
        print(f"Receipt check error: {e}", flush=True)

    save_state(state)


def main():
    # Initialize BFE (32-bit COM)
    from bridge.connection import initialize_bfe, _get_rs
    from bridge.whatsapp import send_whatsapp_message
    
    bfe_active = False
    
    while True:
        if not bfe_active:
            try:
                initialize_bfe()
                print(f"Scrutiny Runner started (32-bit BFE active). Interval: {INTERVAL}s", flush=True)
                bfe_active = True
            except Exception as e:
                print(f"Failed to initialize BFE: {e}. Retrying in 10s...", flush=True)
                time.sleep(10)
                continue

        try:
            run_check(_get_rs, send_whatsapp_message)
        except Exception as e:
            print(f"Scrutiny loop error: {e}", flush=True)
            # If it's a COM or DB error, force re-initialization
            if "com_error" in str(type(e)).lower() or "db" in str(e).lower() or "bfe" in str(e).lower():
                bfe_active = False
                
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
