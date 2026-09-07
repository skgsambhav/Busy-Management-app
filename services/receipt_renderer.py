"""
receipt_renderer.py — Payment Receipt HTML Renderer
Renders a premium, mobile-first Hindi digital payment receipt.
Called from the 64-bit Flask process (uses bfe_client bridge data).
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


def _load_template() -> str:
    tpl_path = os.path.join(_TEMPLATES_DIR, "receipt_whatsapp.html")
    with open(tpl_path, "r", encoding="utf-8") as f:
        return f.read()


def _fmt_amount(val: float) -> str:
    try:
        return f"₹ {abs(float(val)):,.2f}"
    except Exception:
        return "₹ 0.00"


def _parse_date(date_str: str) -> str:
    """Convert YYYY-MM-DD or DD/MM/YYYY for display."""
    if not date_str:
        return ""
    try:
        if "-" in date_str and len(date_str) >= 10:
            parts = date_str[:10].split("-")
            return f"{parts[2]}/{parts[1]}/{parts[0]}"
    except Exception:
        pass
    return date_str


def render_receipt_html(receipt_data: dict, company_info: dict = None, current_balance: str = "") -> str:
    """
    Render the premium Hindi receipt HTML.

    Args:
        receipt_data: dict from bfe_client.get_receipt_voucher_details(vcode)
        company_info: dict from bfe_client.get_company_info() (optional)
        current_balance: str formatted current party balance (optional)

    Returns:
        Complete standalone HTML string ready for R2 upload.
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

    vno = str(receipt_data.get("vno") or receipt_data.get("vchno") or "")
    date_str = _parse_date(str(receipt_data.get("date", "")))
    amount = float(receipt_data.get("amount", 0))
    party_name = str(receipt_data.get("party_name", "Customer"))
    party_name_hi = str(receipt_data.get("party_name_hi", ""))
    party_code = int(receipt_data.get("party_code") or 0)
    mobile = str(receipt_data.get("mobile", ""))
    cash_bank_name = str(receipt_data.get("cash_bank_name", "Cash/Bank"))
    narration = str(receipt_data.get("narration", ""))
    adjustments = receipt_data.get("adjustments", [])

    ctx = {
        "header_b64": _get_header_b64(),
        "upi_qr_b64": _generate_upi_qr_b64(0.0),
        "company": co,
        "vno": vno,
        "date": date_str,
        "amount": amount,
        "party_name": party_name,
        "party_name_hi": party_name_hi,
        "party_code": party_code,
        "mobile": mobile,
        "cash_bank_name": cash_bank_name,
        "narration": narration,
        "adjustments": adjustments,
        "current_balance": current_balance
    }

    template_str = _load_template()
    env = Environment()
    tpl = env.from_string(template_str)
    return tpl.render(**ctx)
