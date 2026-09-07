"""
Central configuration for Busywin App.
All constants, paths, and credentials in one place.
"""

# -----------------------------------------------------------------------
# BFE COM Constants (from GlobalConst.bas)
# -----------------------------------------------------------------------
RECEIPT = 14
SALE = 9
PAYMENT = 19

METHOD_NEWREF = 1
METHOD_ADJUSTMENT = 2
METHOD_APPEND = 3

ACC_MAST = 2
GRP_MAST = 1
SERIES_MAST = 21

# -----------------------------------------------------------------------
# Paths & Credentials
# -----------------------------------------------------------------------
BFE_PREFIX = "Busy2L21"
BUSY_PATH = "C:\\BusyWin\\"
DATA_PATH = "C:\\BusyWin\\Data\\"
COMP_CODE = "COMP0002"
USERNAME  = "admin"
PASSWORD  = "1970"
DB_PASSWORD = "ILoveMyINDIA"

# -----------------------------------------------------------------------
# Accounting Group Codes
# -----------------------------------------------------------------------
# Busy Master Group Codes
SUNDRY_DEBTORS_CODE = 116
SUNDRY_CREDITORS_CODE = 117
CASH_IN_HAND_CODE = 104

# -----------------------------------------------------------------------
# Voucher Type Names (for display)
# -----------------------------------------------------------------------
VCH_TYPE_NAMES = {
    1: "Purchase", 2: "Purc. Return", 8: "Purchase", 9: "Sale", 10: "Sale Return",
    14: "Receipt", 15: "Payment", 16: "Journal", 17: "Contra"
}

# -----------------------------------------------------------------------
# Cloudflare R2 Storage — Invoice & Ledger HTML Storage
# Bucket: gm-sales-invoice-30days  |  TTL: 90 days
# -----------------------------------------------------------------------
R2_ACCOUNT_ID        = "e4b07c12ff976b1c8e5cb58b6fc67391"
R2_ACCESS_KEY_ID     = "c4db66344adfa0054f2371cd1551935d"
R2_SECRET_ACCESS_KEY = "4d2737cbfc06c58d83b9a789d9f2aa582995522ae6e9f982b862968f7dee07e4"
R2_BUCKET_NAME       = "gm-sales-invoice-30days"
R2_ENDPOINT_URL      = "https://e4b07c12ff976b1c8e5cb58b6fc67391.r2.cloudflarestorage.com"
# Public Development URL (enabled on Cloudflare Dashboard)
R2_PUBLIC_BASE_URL   = "https://pub-76fb10221bc945718a2e27ab1fa4fbec.r2.dev"
R2_TTL_DAYS          = 90
