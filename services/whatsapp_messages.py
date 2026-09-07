"""
services/whatsapp_messages.py
Centralized, pure corporate WhatsApp message templates for Gopal Marketing.
Zero emojis, clean bold labels, solid dividers, and natural Hindi+English clarity.
"""

from datetime import datetime


def _clean_date(date_str: str) -> str:
    """Format dates to clean DD/MM/YYYY."""
    if not date_str:
        return datetime.now().strftime("%d/%m/%Y")
    d = str(date_str).strip()
    if len(d) >= 10 and d[4] == "-" and d[7] == "-":
        parts = d[:10].split("-")
        return f"{parts[2]}/{parts[1]}/{parts[0]}"
    return d


def _clean_amount(val) -> str:
    """Format amounts to clean ₹XX,XXX.00 format."""
    if val is None:
        return "₹0.00"
    s = str(val).strip()
    if s.startswith("₹"):
        s = s[1:].strip()
    try:
        num = float(s.replace(",", ""))
        return f"₹{abs(num):,.2f}"
    except Exception:
        return f"₹{s}"


def _build_invoice_whatsapp_msg(vno: str, date_str: str, party_name: str,
                                total, url: str) -> str:
    """
    Build a pure corporate WhatsApp sales bill notification message (zero emojis).
    """
    formatted_date = _clean_date(date_str)
    formatted_total = _clean_amount(total)
    party_clean = str(party_name or "Customer").strip()
    vno_clean = str(vno or "").strip()

    msg  = f"*GOPAL MARKETING — SALES BILL*\n"
    msg += f"────────────────────────\n"
    msg += f"*Party:* {party_clean}\n"
    msg += f"*Bill No:* {vno_clean}\n"
    msg += f"*Date:* {formatted_date}\n"
    msg += f"*Bill Amount:* {formatted_total}\n"
    msg += f"────────────────────────\n"
    msg += f"*View Digital Bill / डिजिटल बिल देखें:*\n"
    msg += f"{url}\n"
    msg += f"────────────────────────\n"
    msg += f"*GOPAL MARKETING*\n"
    msg += f"Green Park Colony, Kharsia Naka, Ambikapur (C.G.)\n"
    msg += f"Phone: 9977414177, 9406040611\n\n"
    msg += f"*Note:* यदि लिंक न खुले, तो कृपया यह नंबर Save करें।"
    return msg


def _build_receipt_whatsapp_msg(receipt_data: dict, current_balance: str = "", url: str = "") -> str:
    """
    Build a pure corporate WhatsApp payment receipt notification message (zero emojis).
    """
    vno = str(receipt_data.get("vno") or receipt_data.get("vchno", "")).strip()
    date_str = _clean_date(receipt_data.get("date", ""))
    amount = float(receipt_data.get("amount", 0))
    formatted_amount = f"₹{amount:,.2f}"
    party_clean = str(receipt_data.get("party_name", "Customer")).strip()
    mode = str(receipt_data.get("cash_bank_name") or "Bank/Cash").strip()

    msg  = f"*GOPAL MARKETING — PAYMENT RECEIPT*\n"
    msg += f"────────────────────────\n"
    msg += f"*Party:* {party_clean}\n"
    msg += f"*Receipt No:* {vno}\n"
    msg += f"*Date:* {date_str}\n"
    msg += f"*Amount Received:* {formatted_amount}\n"
    msg += f"*Payment Mode:* {mode}\n"
    if current_balance:
        bal_str = str(current_balance).strip()
        if "Dr" in bal_str and "बकाया" not in bal_str:
            bal_str += " (बकाया)"
        elif "Cr" in bal_str and "जमा" not in bal_str:
            bal_str += " (जमा)"
        msg += f"*Current Balance:* {bal_str}\n"
    if url:
        msg += f"────────────────────────\n"
        msg += f"*View Digital Receipt / डिजिटल रसीद देखें:*\n"
        msg += f"{url}\n"
    msg += f"────────────────────────\n"
    msg += f"*GOPAL MARKETING*\n"
    msg += f"Green Park Colony, Kharsia Naka, Ambikapur (C.G.)\n"
    msg += f"Phone: 9977414177, 9406040611\n\n"
    msg += f"*Note:* यदि लिंक न खुले, तो कृपया यह नंबर Save करें।"
    return msg


def _build_ledger_whatsapp_msg(party_name: str, balance_text: str,
                               dr_cr: str, url: str, as_on_date: str = "") -> str:
    """
    Build a pure corporate WhatsApp ledger statement notification message (zero emojis).
    """
    party_clean = str(party_name or "Customer").strip()
    date_str = _clean_date(as_on_date)

    dr_cr_clean = str(dr_cr or "").strip().upper()
    bal_str = str(balance_text or "").strip()
    if not bal_str.startswith("₹"):
        try:
            num = float(bal_str.replace(",", ""))
            bal_str = f"₹{abs(num):,.2f}"
        except Exception:
            bal_str = f"₹{bal_str}"

    if dr_cr_clean == "DR":
        bal_display = f"{bal_str} Dr (बकाया)"
    elif dr_cr_clean == "CR":
        bal_display = f"{bal_str} Cr (जमा)"
    else:
        bal_display = f"{bal_str}"

    msg  = f"*GOPAL MARKETING — LEDGER STATEMENT*\n"
    msg += f"────────────────────────\n"
    msg += f"*Party:* {party_clean}\n"
    msg += f"*Date:* {date_str}\n"
    msg += f"*Current Balance:* {bal_display}\n"
    msg += f"────────────────────────\n"
    msg += f"*View Ledger / पूरा लेजर देखें:*\n"
    msg += f"{url}\n"
    msg += f"────────────────────────\n"
    msg += f"*GOPAL MARKETING*\n"
    msg += f"Green Park Colony, Kharsia Naka, Ambikapur (C.G.)\n"
    msg += f"Phone: 9977414177, 9406040611\n\n"
    msg += f"*Note:* यदि लिंक न खुले, तो कृपया यह नंबर Save करें।"
    return msg
