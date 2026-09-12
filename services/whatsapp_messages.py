"""
services/whatsapp_messages.py
Centralized WhatsApp message templates for Gopal Marketing.
Modern, clean, mobile-first corporate style (100% responsive on all mobile screens).
Uses clean bullet points, bold key-values, and standalone clickable URLs.
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


# ── Invoice Message ─────────────────────────────────────────────────────────

def _build_invoice_whatsapp_msg(vno: str, date_str: str, party_name: str,
                                total, url: str) -> str:
    """
    Build a modern mobile-optimized corporate WhatsApp sales invoice notification.
    """
    formatted_date  = _clean_date(date_str)
    formatted_total = _clean_amount(total)
    party_clean     = str(party_name or "Customer").strip()
    vno_clean       = str(vno or "").strip()

    lines = [
        "🧾 *SALES INVOICE*",
        f"▪ *Account:* {party_clean}",
        f"▪ *Invoice No:* {vno_clean}",
        f"▪ *Date:* {formatted_date}",
        f"▪ *Grand Total:* *{formatted_total}*",
    ]

    if url:
        lines += [
            "",
            "🌐 *View Digital Bill:*",
            f"👉 {url}",
        ]

    lines += [
        "",
        "*Gopal Marketing*,",
        "Kharsia Naka, Ambikapur (C.G.)",
        "9977414177 | 9406040611",
        "",
        "_नोट: बिल लिंक खोलने के लिए कृपया यह नंबर Save कर लें।_",
    ]
    return "\n".join(lines)


# ── Receipt Message ─────────────────────────────────────────────────────────

def _build_receipt_whatsapp_msg(receipt_data: dict, current_balance: str = "",
                                url: str = "") -> str:
    """
    Build a modern mobile-optimized corporate WhatsApp payment receipt notification.
    """
    vno              = str(receipt_data.get("vno") or receipt_data.get("vchno", "")).strip()
    date_str         = _clean_date(receipt_data.get("date", ""))
    amount           = float(receipt_data.get("amount", 0))
    formatted_amount = f"₹{amount:,.2f}"
    party_clean      = str(receipt_data.get("party_name", "Customer")).strip()
    mode             = str(receipt_data.get("cash_bank_name") or "Bank/Cash").strip()

    lines = [
        "✅ *PAYMENT RECEIPT*",
        f"▪ *Account:* {party_clean}",
        f"▪ *Receipt No:* {vno}",
        f"▪ *Date:* {date_str}",
        f"▪ *Amount Received:* *{formatted_amount}*",
        f"▪ *Payment Mode:* {mode}",
    ]

    if current_balance:
        bal_str = str(current_balance).strip()
        if "Dr" in bal_str and "बकाया" not in bal_str:
            bal_str += " (बकाया)"
        elif "Cr" in bal_str and "जमा" not in bal_str:
            bal_str += " (जमा)"
        lines.append(f"▪ *Current Balance:* *{bal_str}*")

    if url:
        lines += [
            "",
            "🌐 *View Digital Receipt:*",
            f"👉 {url}",
        ]

    lines += [
        "",
        "*Gopal Marketing*,",
        "Kharsia Naka, Ambikapur (C.G.)",
        "9977414177 | 9406040611",
        "",
        "_नोट: रसीद लिंक खोलने के लिए कृपया यह नंबर Save कर लें।_",
    ]
    return "\n".join(lines)


# ── Ledger Message ──────────────────────────────────────────────────────────

def _build_ledger_whatsapp_msg(party_name: str, balance_text: str,
                               dr_cr: str, url: str, as_on_date: str = "") -> str:
    """
    Build a modern mobile-optimized corporate WhatsApp ledger statement notification.
    """
    party_clean  = str(party_name or "Customer").strip()
    date_str     = _clean_date(as_on_date)

    dr_cr_clean  = str(dr_cr or "").strip().upper()
    bal_str      = str(balance_text or "").strip()
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
        bal_display = bal_str

    lines = [
        "📋 *LEDGER STATEMENT*",
        f"▪ *Account:* {party_clean}",
        f"▪ *Date:* {date_str}",
        f"▪ *Current Balance:* *{bal_display}*",
    ]

    if url:
        lines += [
            "",
            "🌐 *View Full Ledger:*",
            f"👉 {url}",
        ]

    lines += [
        "",
        "*Gopal Marketing*,",
        "Kharsia Naka, Ambikapur (C.G.)",
        "9977414177 | 9406040611",
        "",
        "_नोट: लेजर लिंक खोलने के लिए कृपया यह नंबर Save कर लें।_",
    ]
    return "\n".join(lines)

