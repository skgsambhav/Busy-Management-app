"""
Database connection management - BFE COM initialization & ADODB helpers.
"""

import win32com.client
import pythoncom
from config import BFE_PREFIX, BUSY_PATH, DATA_PATH, COMP_CODE, USERNAME, PASSWORD, DB_PASSWORD

# -----------------------------------------------------------------------
# Global BFE objects (initialized once, shared across all bridge modules)
# -----------------------------------------------------------------------
g_dm = None   # CDataManager
g_cc = None   # CCompany
g_ms = None   # CMasterServices
g_ts = None   # CTranServices
g_os = None   # COtherServices
g_conn = None # ADODB.Connection


def g_conn_ref():
    """Return the global ADODB connection (for modules that need it)."""
    return g_conn


def initialize_bfe():
    """Initialize BFE COM objects and open company database."""
    global g_dm, g_cc, g_ms, g_ts, g_os, g_conn
    
    pythoncom.CoInitialize()
    
    # 1. Open BFE
    g_dm = win32com.client.Dispatch(f"{BFE_PREFIX}.CDataManager")
    g_dm.OpenCompDataBase(BUSY_PATH, DATA_PATH, COMP_CODE, USERNAME, PASSWORD)
    
    g_cc = win32com.client.Dispatch(f"{BFE_PREFIX}.CCompany")
    g_ms = win32com.client.Dispatch(f"{BFE_PREFIX}.CMasterServices")
    g_ts = win32com.client.Dispatch(f"{BFE_PREFIX}.CTranServices")
    g_os = win32com.client.Dispatch(f"{BFE_PREFIX}.COtherServices")
    
    inval_msg = ""
    if not g_cc.Load(inval_msg):
        raise Exception(f"Could not load company config: {inval_msg}")
        
    # 2. Open ADODB for fast reads
    g_conn = win32com.client.Dispatch("ADODB.Connection")
    db_path = f"{DATA_PATH}{COMP_CODE}\\db12026.bds"
    conn_str = f"Provider=Microsoft.Jet.OLEDB.4.0;Data Source={db_path};Jet OLEDB:Database Password={DB_PASSWORD};"
    g_conn.Open(conn_str)
    
    return True


def format_out_date(dt_val, fallback=""):
    """Format any date value to DD-MM-YYYY."""
    if not dt_val: return fallback
    d_str = str(dt_val)[:10]
    if "-" in d_str:
        parts = d_str.split("-")
        if len(parts) == 3 and len(parts[0]) == 4:
            return f"{parts[2]}-{parts[1]}-{parts[0]}"
    return d_str


def _get_rs(sql):
    """Execute SQL and return an ADODB Recordset."""
    rs = win32com.client.Dispatch("ADODB.Recordset")
    rs.Open(sql, g_conn)
    return rs
