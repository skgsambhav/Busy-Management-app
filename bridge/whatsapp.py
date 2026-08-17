import json
import os
import re
import urllib.request
import urllib.parse

CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "whatsapp_config.json")

DEFAULT_CONFIG = {
    "api_url": "https://waapi.dumx.tech/api/message/send-text",
    "api_key": "",
    "client_id": ""
}

def load_whatsapp_config():
    if not os.path.exists(CONFIG_PATH):
        return DEFAULT_CONFIG
    try:
        with open(CONFIG_PATH, "r") as f:
            return json.load(f)
    except:
        return DEFAULT_CONFIG

def save_whatsapp_config(config):
    try:
        with open(CONFIG_PATH, "w") as f:
            json.dump(config, f, indent=4)
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}

def parse_and_clean_phone_numbers(phone_str):
    """
    Parse a phone string containing one or multiple numbers separated by ;, ,, /, &, newline, etc.
    Returns a list of standardized 12-digit Indian phone numbers (e.g. ['918435015391', '916266738509']).
    """
    if not phone_str:
        return []
        
    raw_tokens = re.split(r'[;,\/&\n]+', str(phone_str))
    valid_numbers = []
    
    for token in raw_tokens:
        digits = re.sub(r'\D', '', token)
        if not digits:
            continue
            
        if len(digits) == 11 and digits.startswith('0'):
            digits = digits[1:]
            
        if len(digits) == 10:
            digits = "91" + digits
        elif len(digits) == 12 and digits.startswith('91'):
            pass
        elif len(digits) > 10:
            digits = "91" + digits[-10:]
        else:
            continue
            
        if digits not in valid_numbers:
            valid_numbers.append(digits)
            
    return valid_numbers

def send_whatsapp_message(to_number, message_text):
    phone_list = parse_and_clean_phone_numbers(to_number)
    if not phone_list:
        raise Exception(f"No valid 10-digit mobile number found in '{to_number}'")

    config = load_whatsapp_config()
    api_url = config.get("api_url") or "https://waapi.dumx.tech/api/message/send-text"
    api_key = config.get("api_key")
    client_id = config.get("client_id")
    
    if not api_key or not client_id:
        raise Exception("WhatsApp API settings are not fully configured. Please configure them in Settings.")
        
    last_res = None
    success_count = 0
    errors = []

    for num in phone_list:
        payload = {
            "clientId": client_id,
            "to": num,
            "message": message_text
        }
        
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(api_url, data=data, method="POST")
        req.add_header("x-api-key", api_key)
        req.add_header("Content-Type", "application/json")
        req.add_header("User-Agent", "curl/7.88.1")
        
        try:
            with urllib.request.urlopen(req, timeout=15) as res:
                res_body = res.read().decode("utf-8")
                last_res = json.loads(res_body)
                success_count += 1
        except urllib.error.HTTPError as e:
            err_content = e.read().decode("utf-8")
            try:
                err_json = json.loads(err_content)
                err_msg = err_json.get("message") or err_json.get("error") or err_content
            except:
                err_msg = err_content
            errors.append(f"{num}: {err_msg}")
        except Exception as e:
            errors.append(f"{num}: {str(e)}")

    if success_count > 0:
        return {
            "success": True,
            "response": last_res,
            "sent_to": phone_list,
            "count": success_count,
            "total": len(phone_list),
            "errors": errors
        }
    else:
        err_detail = "; ".join(errors) if errors else "Failed to send message to recipient(s)"
        raise Exception(f"WhatsApp API Error: {err_detail}")

def send_whatsapp_media(to_number, media_url, filename="Invoice.pdf", caption=""):
    phone_list = parse_and_clean_phone_numbers(to_number)
    if not phone_list:
        raise Exception(f"No valid 10-digit mobile number found in '{to_number}'")

    config = load_whatsapp_config()
    api_url = config.get("api_url") or "https://waapi.dumx.tech/api/message/send-text"
    if "send-text" in api_url:
        media_api_url = api_url.replace("send-text", "send-media")
    else:
        media_api_url = api_url
        
    api_key = config.get("api_key")
    client_id = config.get("client_id")
    
    if not api_key or not client_id:
        raise Exception("WhatsApp API settings are not fully configured.")
        
    clean_filename = str(filename).strip() if filename else "Invoice.pdf"
    if not clean_filename.lower().endswith(".pdf"):
        clean_filename += ".pdf"

    last_res = None
    success_count = 0
    errors = []

    for num in phone_list:
        payload = {
            "clientId": client_id,
            "to": num,
            "mediaUrl": media_url,
            "mediaType": "document",
            "filename": clean_filename,
            "fileName": clean_filename,
            "documentName": clean_filename,
            "name": clean_filename,
            "title": clean_filename,
            "mimetype": "application/pdf",
            "caption": caption
        }
        
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(media_api_url, data=data, method="POST")
        req.add_header("x-api-key", api_key)
        req.add_header("Content-Type", "application/json")
        req.add_header("User-Agent", "curl/7.88.1")
        
        try:
            with urllib.request.urlopen(req, timeout=30) as res:
                res_body = res.read().decode("utf-8")
                last_res = json.loads(res_body)
                success_count += 1
        except urllib.error.HTTPError as e:
            err_content = e.read().decode("utf-8")
            try:
                err_json = json.loads(err_content)
                err_msg = err_json.get("message") or err_json.get("error") or err_content
            except:
                err_msg = err_content
            errors.append(f"{num}: {err_msg}")
        except Exception as e:
            errors.append(f"{num}: {str(e)}")

    if success_count > 0:
        return {
            "success": True,
            "response": last_res,
            "sent_to": phone_list,
            "count": success_count,
            "total": len(phone_list),
            "errors": errors
        }
    else:
        err_detail = "; ".join(errors) if errors else "Failed to send media to recipient(s)"
        raise Exception(f"WhatsApp API Error: {err_detail}")

def format_invoice_msg_en(data):
    msg = f"Hello {data['party_name']},\n\n"
    msg += f"Your invoice *{data['vno']}* dated *{data['date']}* has been generated.\n\n"
    msg += f"Total Amount: *₹{data['total_amount']:,.2f}*\n\n"
    msg += "Items:\n"
    for i, it in enumerate(data['items']):
        msg += f"{i+1}. {it['item_name']} - {it['qty']} {it['unit']} @ ₹{it['price']:,.2f} = ₹{it['amount']:,.2f}\n\n"
    
    if data.get('bill_sundries'):
        msg += "Tax / Sundries:\n"
        for s in data['bill_sundries']:
            msg += f"- {s['name']}: ₹{s['amount']:,.2f}\n"
        msg += "\n"
            
    msg += f"Total Qty: *{data['total_qty']}*\n\n"
    msg += "Thank you for your business!"
    return msg

def format_invoice_msg_hi(data):
    party_name = data.get('party_name_hi') or data['party_name']
    msg = f"नमस्ते {party_name},\n\n"
    msg += f"आपका बिल नंबर *{data['vno']}* दिनांक *{data['date']}* को जारी कर दिया गया है।\n\n"
    msg += f"कुल राशि: *₹{data['total_amount']:,.2f}*\n\n"
    msg += "सामग्री (Items):\n"
    for i, it in enumerate(data['items']):
        item_name = it.get('item_name_hi') or it['item_name']
        msg += f"{i+1}. {item_name} - {it['qty']} {it['unit']} @ ₹{it['price']:,.2f} = ₹{it['amount']:,.2f}\n\n"
        
    if data.get('bill_sundries'):
        msg += "टैक्स / अन्य शुल्क:\n"
        for s in data['bill_sundries']:
            msg += f"- {s['name']}: ₹{s['amount']:,.2f}\n"
        msg += "\n"
            
    msg += f"कुल मात्रा: *{data['total_qty']}*\n\n"
    msg += "*GOPAL MARKETING*"
    return msg

def format_invoice_msg_both(data):
    party_en = data['party_name']
    party_hi = data.get('party_name_hi') or party_en
    party_display = f"{party_en} / {party_hi}" if party_en != party_hi else party_en
    
    msg = f"Hello / नमस्ते {party_display},\n\n"
    msg += f"Invoice / बिल: *{data['vno']}* | Date / दिनांक: *{data['date']}*\n"
    msg += f"Total Amt / कुल राशि: *₹{data['total_amount']:,.2f}*\n\n"
    msg += "Items / सामग्री:\n"
    for i, it in enumerate(data['items']):
        name_en = it['item_name']
        name_hi = it.get('item_name_hi') or name_en
        name_display = f"{name_en} ({name_hi})" if name_en != name_hi else name_en
        msg += f"{i+1}. {name_display} - {it['qty']} {it['unit']} @ ₹{it['price']:,.2f} = ₹{it['amount']:,.2f}\n\n"
        
    if data.get('bill_sundries'):
        msg += "Charges / Sundries:\n"
        for s in data['bill_sundries']:
            msg += f"- {s['name']}: ₹{s['amount']:,.2f}\n"
        msg += "\n"
            
    msg += f"Total Qty / कुल मात्रा: *{data['total_qty']}*\n\n"
    msg += "Thank you / धन्यवाद!"
    return msg

def send_whatsapp_invoice(vcode, language, phone):
    from bridge.sales import get_sales_voucher_details
    data = get_sales_voucher_details(vcode)
    if "error" in data:
        return data
        
    if language == "hindi":
        msg = format_invoice_msg_hi(data)
    elif language == "both":
        msg = format_invoice_msg_both(data)
    else:
        msg = format_invoice_msg_en(data)
        
    return send_whatsapp_message(phone, msg)

def send_whatsapp_ledger(party_code, phone):
    from bridge.ledger import get_ledger, get_outstanding_bills
    from bridge.connection import _get_rs
    
    party_name = "Customer"
    party_name_hi = ""
    try:
        rs = _get_rs(f"SELECT Name, NameSL FROM Master1 WHERE Code = {party_code}")
        if not rs.EOF:
            party_name = str(rs.Fields("Name").Value or "").strip()
            party_name_hi = str(rs.Fields("NameSL").Value or "").strip()
        rs.Close()
    except:
        pass
        
    disp_name = party_name_hi or party_name
    ledger_data = get_ledger(party_code)
    
    op_bal = ledger_data["op_bal"]
    transactions = ledger_data["transactions"]
    
    running = op_bal
    for t in transactions:
        running += t["amount"]
        
    def fmt_bal(val):
        if val < 0:
            return f"₹{abs(val):,.2f} Dr"
        elif val > 0:
            return f"₹{val:,.2f} Cr"
        return "₹0.00"
        
    msg = f"*{disp_name}*\n"
    msg += f"📌 *खाता विवरण (Account Statement)*\n"
    msg += f"━━━━━━━━━━━━━━━━━━\n\n"
    
    msg += f"🔻 *कुल बकाया (Net Balance):*\n"
    msg += f"👉 *{fmt_bal(running)}*\n\n"

    # Fetch pending bills
    try:
        pending_bills = get_outstanding_bills(party_code)
        if pending_bills:
            msg += f"━━━━━━━━━━━━━━━━━━\n"
            msg += f"📋 *पेंडिंग बिल (Pending Bills)*\n\n"
            total_pending = 0
            for b in pending_bills:
                b_amt = b["balance"]
                total_pending += b_amt
                
                # Format date compactly (e.g., DD/MM from DD/MM/YYYY)
                dt_str = b['date']
                if len(dt_str) >= 10 and '/' in dt_str:
                    dt_str = dt_str[:5]  # Take "DD/MM"
                
                msg += f"🔸 *{b['bill_no']}* ({dt_str})\n"
                msg += f"   ▶ ₹{b_amt:,.2f}\n\n"
            
            msg += f"💰 *कुल पेंडिंग (Total): ₹{total_pending:,.2f}*\n"
    except Exception as e:
        pass

    msg += f"━━━━━━━━━━━━━━━━━━\n"
    msg += f"कृपया समय पर भुगतान करें। 🙏\n\n"
    msg += "🏬 *GOPAL MARKETING*\n"
    msg += "📍 AMBIKAPUR\n"
    msg += "📞 9977414177, 9406040611"
    
    return send_whatsapp_message(phone, msg)
