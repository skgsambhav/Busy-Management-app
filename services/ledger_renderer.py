"""
ledger_renderer.py — Party Ledger HTML Renderer
Renders a premium, mobile-first Hindi ledger / account statement.
Called from the 64-bit Flask process (no COM needed — uses bfe_client bridge).
"""

import os
import io
import base64
import qrcode
from jinja2 import Environment

_TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")

# Cache for header image base64
_HEADER_B64 = ""
def _get_header_b64() -> str:
    global _HEADER_B64
    if not _HEADER_B64:
        p = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "hdr_compact_b64.txt")
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                _HEADER_B64 = f.read().strip()
    return _HEADER_B64


def _generate_upi_qr_b64(amount: float = 0.0) -> str:
    """Generate instant offline UPI QR code in base64 format."""
    try:
        upi_url = "upi://pay?pa=gopalmarketing@ybl&pn=GOPAL%20MARKETING&cu=INR"
        if amount and amount > 0:
            upi_url += f"&am={amount:.2f}"
        qr = qrcode.QRCode(version=1, box_size=4, border=1)
        qr.add_data(upi_url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="#2b0409", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode("utf-8")
    except Exception:
        return ""


COMPANY_INFO_DEFAULT = {
    "name": "GOPAL MARKETING",
    "name_hi": "गोपाल मार्केटिंग",
    "address": "Green Park Colony Near Bharat Mata chauk, Kharsia Naka, Ambikapur, Surguja, Chhattisgarh - 497001",
    "phone1": "9977414177",
    "phone2": "9406040611",
}

VCH_TYPE_LABELS = {
    9: "बिक्री",
    14: "भुगतान प्राप्त",
    15: "भुगतान",
    1: "क्रय",
    2: "क्रय वापसी",
    10: "बिक्री वापसी",
    16: "जर्नल",
    17: "कांट्रा"
}


def _load_template() -> str:
    tpl_path = os.path.join(_TEMPLATES_DIR, "ledger_whatsapp.html")
    with open(tpl_path, "r", encoding="utf-8") as f:
        return f.read()


def _fmt_amount(val: float) -> str:
    try:
        return f"₹ {abs(float(val)):,.2f}"
    except Exception:
        return "₹ 0.00"


def _fmt_bal(val: float) -> dict:
    """Return formatted balance with Dr/Cr label."""
    val = float(val)
    if val < 0:
        return {"text": f"₹{abs(val):,.2f}", "label": "Dr", "dr": True}
    elif val > 0:
        return {"text": f"₹{val:,.2f}", "label": "Cr", "dr": False}
    return {"text": "₹0.00", "label": "", "dr": False}


def _parse_date(date_str: str) -> str:
    """Convert YYYY-MM-DD to DD/MM/YYYY."""
    if not date_str:
        return ""
    try:
        if "-" in date_str and len(date_str) >= 10:
            parts = date_str[:10].split("-")
            return f"{parts[2]}/{parts[1]}/{parts[0]}"
    except Exception:
        pass
    return date_str


def render_ledger_html(party_name: str, party_name_hi: str,
                       ledger_data: dict, pending_bills: list,
                       company_info: dict = None) -> str:
    """
    Render the premium Hindi ledger HTML.

    Args:
        party_name: English party name
        party_name_hi: Hindi party name (NameSL)
        ledger_data: dict from bfe_client.get_ledger(party_code)
        pending_bills: list from bfe_client.get_outstanding_bills(party_code)
        company_info: dict from bfe_client.get_company_info() (optional)

    Returns:
        Complete standalone HTML string.
    """
    company = company_info or COMPANY_INFO_DEFAULT

    addr_parts = [
        str(company.get("address1") or "").strip(),
        str(company.get("address2") or "").strip(),
        str(company.get("address3") or "").strip(),
        str(company.get("address4") or "").strip(),
    ]
    raw_addr = ", ".join([p for p in addr_parts if p])
    if not raw_addr or len(raw_addr) < 30 or "Kharsia" not in raw_addr:
        final_address = COMPANY_INFO_DEFAULT["address"]
    else:
        final_address = raw_addr

    co = {
        "name": company.get("company_name") or company.get("name") or COMPANY_INFO_DEFAULT["name"],
        "name_hi": COMPANY_INFO_DEFAULT["name_hi"],
        "address": final_address,
        "phone1": COMPANY_INFO_DEFAULT["phone1"],
        "phone2": COMPANY_INFO_DEFAULT["phone2"],
    }

    # ─── Running Balance ────────────────────────────────────────────────────
    op_bal = float(ledger_data.get("op_bal", 0))
    transactions = ledger_data.get("transactions", [])

    running = op_bal
    txns = []
    for t in transactions:
        amt = float(t.get("amount", 0))
        running += amt
        type_code = int(t.get("type_code", 0))

        # Dr/Cr label: negative amount = Dr (sale), positive = Cr (receipt)
        is_dr = amt < 0
        txns.append({
            "date": _parse_date(str(t.get("date", ""))),
            "vch_no": t.get("vch_no", ""),
            "type_label": VCH_TYPE_LABELS.get(type_code, f"VCH-{type_code}"),
            "narration": t.get("narration", "") or t.get("opp_account", ""),
            "amount": _fmt_amount(abs(amt)),
            "amount_raw": abs(amt),
            "is_dr": is_dr,
            "running_bal": _fmt_bal(running)
        })

    # Show last 50 transactions (most recent first for display)
    recent_txns = txns[-50:][::-1]

    net_bal = _fmt_bal(running)

    # ─── Pending Bills ──────────────────────────────────────────────────────
    bills = []
    total_pending = 0.0
    for b in pending_bills:
        amt = float(b.get("balance", 0))
        total_pending += amt
        bills.append({
            "bill_no": b.get("bill_no", ""),
            "date": _parse_date(str(b.get("date", ""))),
            "original": _fmt_amount(b.get("original_amount", 0)),
            "balance": _fmt_amount(amt),
            "balance_raw": amt
        })

    display_name = party_name

    ctx = {
        "header_b64": _get_header_b64(),
        "upi_qr_b64": _generate_upi_qr_b64(total_pending if total_pending > 0 else (abs(running) if running < 0 else 0.0)),
        "company": co,
        "party_name": display_name,
        "party_name_en": party_name,
        "mobile": ledger_data.get("mobile", ""),
        "address": " ".join(filter(None, [
            ledger_data.get("address1", ""),
            ledger_data.get("address2", ""),
            ledger_data.get("address3", "")
        ])).strip(),
        "gst": ledger_data.get("gst", ""),
        "op_bal": _fmt_bal(op_bal),
        "net_bal": net_bal,
        "total_pending": _fmt_amount(total_pending),
        "total_pending_raw": total_pending,
        "pending_bills": bills,
        "transactions": recent_txns,
        "txn_count": len(transactions)
    }

    template_str = _load_template()
    env = Environment()
    tpl = env.from_string(template_str)
    return tpl.render(**ctx)
