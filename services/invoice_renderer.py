"""
invoice_renderer.py — Sales Invoice HTML Renderer
Renders a premium, mobile-first Hindi invoice from Busy sales voucher data.
Called from the 64-bit Flask process (no COM needed — uses bfe_client bridge).
"""

import os
import io
import base64
import qrcode
from flask import render_template_string
from jinja2 import Environment, FileSystemLoader


# ─── Template Path ──────────────────────────────────────────────────────────
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
        upi_url = "upi://pay?pa=gopalmarketing@ybl&pn=Gopal%20Marketing&cu=INR"
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

# Company Info (static defaults — overridden by live data when available)
COMPANY_INFO_DEFAULT = {
    "name": "GOPAL MARKETING",
    "name_hi": "गोपाल मार्केटिंग",
    "address": "Green Park Colony Near Bharat Mata chauk, Kharsia Naka, Ambikapur, Surguja, Chhattisgarh - 497001",
    "address_hi": "ग्रीन पार्क कॉलोनी, भारत माता चौक के पास, खरसिया नाका, अंबिकापुर, सरगुजा (छ.ग.) - 497001",
    "phone1": "9977414177",
    "phone2": "9406040611",
    "gst": "22AXYPG6249E1Z9",
    "email": "gmgopalmarketing@gmail.com"
}


def _load_template() -> str:
    """Load the invoice HTML template from the templates directory."""
    tpl_path = os.path.join(_TEMPLATES_DIR, "invoice_whatsapp.html")
    with open(tpl_path, "r", encoding="utf-8") as f:
        return f.read()


def _fmt_num(val: float) -> str:
    """Format a number with comma separators and 2 decimals (NO currency symbol)."""
    try:
        return f"{abs(float(val)):,.2f}"
    except Exception:
        return "0.00"


def _fmt_amount(val: float) -> str:
    """Format a number as Indian currency string with 1 space gap after ₹."""
    try:
        return f"₹ {abs(float(val)):,.2f}"
    except Exception:
        return "₹ 0.00"


def _fmt_qty(val: float) -> str:
    """Format quantity: remove .00 if it's a whole number."""
    try:
        v = float(val)
        return str(int(v)) if v == int(v) else f"{v:.2f}"
    except Exception:
        return str(val)


def _parse_date(date_str: str) -> str:
    """Convert YYYY-MM-DD to DD/MM/YYYY for display."""
    if not date_str:
        return ""
    try:
        if "-" in date_str and len(date_str) >= 10:
            parts = date_str[:10].split("-")
            return f"{parts[2]}/{parts[1]}/{parts[0]}"
    except Exception:
        pass
    return date_str


def render_invoice_html(voucher_data: dict, company_info: dict = None) -> str:
    """
    Render the premium Hindi invoice HTML.

    Args:
        voucher_data: dict from bfe_client.get_sales_voucher_details(vcode)
        company_info: dict from bfe_client.get_company_info() (optional)

    Returns:
        Complete standalone HTML string ready for R2 upload.
    """
    company = company_info or COMPANY_INFO_DEFAULT

    # Build complete address (combine all address lines; fallback to full landmark address if incomplete)
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

    # Normalise company info keys
    co = {
        "name": company.get("company_name") or company.get("name") or COMPANY_INFO_DEFAULT["name"],
        "name_hi": COMPANY_INFO_DEFAULT["name_hi"],
        "address": final_address,
        "address_hi": COMPANY_INFO_DEFAULT["address_hi"],
        "phone1": COMPANY_INFO_DEFAULT["phone1"],
        "phone2": COMPANY_INFO_DEFAULT["phone2"],
        "gst": company.get("gst_no", "") or COMPANY_INFO_DEFAULT["gst"],
        "email": company.get("email", "") or COMPANY_INFO_DEFAULT["email"]
    }

    # Format items for template
    items = []
    for it in voucher_data.get("items", []):
        unit_en = str(it.get("unit_en") or it.get("unit") or "").strip()
        unit_hi_db = (it.get("unit_hi") or "").strip()
        
        # Use Busy DB Hindi name if set in Unit Master (Second Language)
        # Otherwise show English unit name exactly as-is (PCS, BOX, PKD etc.)
        # No hardcoded translations — respect what user has set in Busy
        unit_hi = unit_hi_db if unit_hi_db else unit_en
            
        items.append({
            "sr_no": it.get("sr_no", ""),
            "name": it.get("item_name_hi") or it.get("item_name", ""),
            "name_en": it.get("item_name", ""),
            "unit": unit_hi,
            "qty": _fmt_qty(it.get("qty", 0)),
            "price": _fmt_num(it.get("price", 0)),
            "amount": _fmt_num(it.get("amount", 0)),
            "amount_raw": float(it.get("amount", 0))
        })

    # Format sundries
    sundries = []
    for s in voucher_data.get("bill_sundries", []):
        amt = float(s.get("amount", 0))
        sundries.append({
            "name": s.get("name", ""),
            "amount": _fmt_num(amt),
            "amount_raw": amt,
            "is_deduction": amt < 0
        })

    # GST breakdown from sundries
    cgst_total = 0.0
    sgst_total = 0.0
    igst_total = 0.0
    other_sundries = []
    for s in sundries:
        nm = s["name"].upper()
        if "CGST" in nm:
            cgst_total += abs(s["amount_raw"])
        elif "SGST" in nm:
            sgst_total += abs(s["amount_raw"])
        elif "IGST" in nm:
            igst_total += abs(s["amount_raw"])
        else:
            other_sundries.append(s)

    party_name = voucher_data.get("party_name", "")
    party_name_en = voucher_data.get("party_name", "")

    ctx = {
        "header_b64": _get_header_b64(),
        "company": co,
        "vno": voucher_data.get("vno", ""),
        "date": _parse_date(voucher_data.get("date", "")),
        "party_name": party_name,
        "party_name_en": party_name_en,
        "address": (voucher_data.get("address") or "").replace("\n", ", ").strip(),
        "mobile": voucher_data.get("mobile", ""),
        "items": items,
        "sundries": sundries,
        "other_sundries": other_sundries,
        "cgst_total": _fmt_num(cgst_total) if cgst_total else None,
        "sgst_total": _fmt_num(sgst_total) if sgst_total else None,
        "igst_total": _fmt_num(igst_total) if igst_total else None,
        "item_total": _fmt_num(voucher_data.get("item_total", 0)),
        "total_qty": _fmt_qty(voucher_data.get("total_qty", 0)),
        "grand_total": _fmt_amount(voucher_data.get("total_amount", 0)),
        "grand_total_raw": float(voucher_data.get("total_amount", 0)),
        "upi_qr_b64": _generate_upi_qr_b64(float(voucher_data.get("total_amount", 0))),
        # Loyalty Points — only > 0 when this voucher actually earned points
        "points_opening": float(voucher_data.get("points_opening", 0)),
        "points_earned": float(voucher_data.get("points_earned", 0)),
        "points_redeemed": float(voucher_data.get("points_redeemed", 0)),
        "total_points": float(voucher_data.get("total_points", 0)),
    }

    template_str = _load_template()
    env = Environment()
    tpl = env.from_string(template_str)
    return tpl.render(**ctx)
