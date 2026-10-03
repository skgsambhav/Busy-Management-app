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
# Bucket: gopalmarketing  |  Domain: https://gopalmarketing.in
# -----------------------------------------------------------------------
R2_ACCOUNT_ID        = "0b965e15d5c6d875a1507dd390b7c5df"
R2_ACCESS_KEY_ID     = "4f850e2e932a0e3de875a3c551e062de"
R2_SECRET_ACCESS_KEY = "c8f4b590207298f2dcdc3caa138640cb6ed72cfeea9f97ec4705034f22dbf9c6"
R2_BUCKET_NAME       = "gopalmarketing"
R2_ENDPOINT_URL      = "https://0b965e15d5c6d875a1507dd390b7c5df.r2.cloudflarestorage.com"
R2_PUBLIC_BASE_URL   = "https://doc.gopalmarketing.in"
R2_DOC_PREFIX        = "doc"
R2_TTL_DAYS          = 180
