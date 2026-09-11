"""
Master data queries - Parties, Cash/Bank accounts, Company info.
"""

import win32com.client
from config import SUNDRY_DEBTORS_CODE, DATA_PATH, COMP_CODE, DB_PASSWORD
from bridge.connection import _get_rs, g_conn_ref


def update_master_namesl(master_code: int, name_sl: str):
    """Update the Hindi (Second Language) name for any Master."""
    g_conn = g_conn_ref()
    try:
        safe_sl = name_sl.replace("'", "''")
        g_conn.Execute(f"UPDATE Master1 SET NameSL = '{safe_sl}', PrintNameSL = '{safe_sl}' WHERE Code = {master_code}")
        return {"success": True}
    except Exception as e:
        raise Exception(f"Failed to update Master NameSL: {e}")


def get_parties():
    """Get all Sundry Debtor ledgers with mobile numbers."""
    sql = f"""
        SELECT m.Code, m.Name, m.NameSL, m.ParentGrp,
               (SELECT Name FROM Master1 WHERE Code = m.ParentGrp) AS GrpName,
               mai.Mobile
        FROM Master1 m
        LEFT JOIN MasterAddressInfo mai ON m.Code = mai.MasterCode
        WHERE m.MasterType = 2
          AND m.ParentGrp IN (
              SELECT Code FROM Master1 
              WHERE MasterType = 1 
              AND (Code = {SUNDRY_DEBTORS_CODE} 
                OR ParentGrp = {SUNDRY_DEBTORS_CODE}
                OR Code = 111 
                OR ParentGrp = 111
                OR Code = 112
                OR ParentGrp = 112)
          )
        ORDER BY m.Name
    """
    rst = _get_rs(sql)
    
    parties = []
    while not rst.EOF:
        parties.append({
            "code": int(rst.Fields("Code").Value),
            "name": str(rst.Fields("Name").Value or "").strip().upper(),
            "name_sl": str(rst.Fields("NameSL").Value or "").strip(),
            "group": str(rst.Fields("GrpName").Value or "").strip().upper(),
            "mobile": str(rst.Fields("Mobile").Value or "").strip()
        })
        rst.MoveNext()
    rst.Close()
    return parties


def get_suppliers():
    """Get all Sundry Creditor ledgers (for Purchase Entry)."""
    from config import SUNDRY_CREDITORS_CODE
    sql = f"""
        SELECT m.Code, m.Name, m.NameSL, m.ParentGrp,
               (SELECT Name FROM Master1 WHERE Code = m.ParentGrp) AS GrpName
        FROM Master1 m
        WHERE m.MasterType = 2
          AND m.ParentGrp IN (
              SELECT Code FROM Master1 
              WHERE MasterType = 1 
              AND (Code = {SUNDRY_CREDITORS_CODE} 
                OR ParentGrp = {SUNDRY_CREDITORS_CODE}
                OR Code = 111
                OR ParentGrp = 111
                OR Code = 112
                OR ParentGrp = 112)
          )
        ORDER BY m.Name
    """
    rst = _get_rs(sql)
    
    suppliers = []
    while not rst.EOF:
        suppliers.append({
            "code": int(rst.Fields("Code").Value),
            "name": str(rst.Fields("Name").Value or "").strip().upper(),
            "name_sl": str(rst.Fields("NameSL").Value or "").strip(),
            "group": str(rst.Fields("GrpName").Value or "").strip().upper()
        })
        rst.MoveNext()
    rst.Close()
    return suppliers


def get_cash_bank_accounts():
    """Get Cash and Bank accounts."""
    sql = """
        SELECT m.Code, m.Name, 
               (SELECT Name FROM Master1 WHERE Code = m.ParentGrp) AS GrpName
        FROM Master1 m
        WHERE m.MasterType = 2
          AND m.ParentGrp IN (
              SELECT Code FROM Master1 
              WHERE MasterType = 1 
              AND Name IN ('Bank Accounts', 'Cash-in-Hand', 'Cash In Hand', 
                           'Bank A/Cs', 'Cash')
          )
        ORDER BY m.Name
    """
    rst = _get_rs(sql)
    accounts = []
    while not rst.EOF:
        accounts.append({
            "code": int(rst.Fields("Code").Value),
            "name": str(rst.Fields("Name").Value or "").strip(),
            "group": str(rst.Fields("GrpName").Value or "").strip()
        })
        rst.MoveNext()
    rst.Close()
    return accounts


def get_company_info():
    """Get company details from root db.bds."""
    db_main = f"{DATA_PATH}{COMP_CODE}\\db.bds"
    conn_str = f"Provider=Microsoft.Jet.OLEDB.4.0;Data Source={db_main};Jet OLEDB:Database Password={DB_PASSWORD};"
    conn = win32com.client.Dispatch("ADODB.Connection")
    
    comp_info = {}
    try:
        conn.Open(conn_str)
        rs = conn.Execute("SELECT TOP 1 * FROM Company")
        if not rs[0].EOF:
            def val(col):
                try:
                    v = rs[0].Fields(col).Value
                    return str(v).strip() if v else ""
                except:
                    return ""
            
            comp_info = {
                "name": val("PrintName") or val("Name"),
                "address1": val("Address1"),
                "address2": val("Address2"),
                "address3": val("Address3"),
                "address4": val("Address4"),
                "phone": val("TelNo"),
                "email": val("Email"),
                "gstin": val("GSTNo") or val("ITPAN")
            }
        rs[0].Close()
    except Exception as e:
        comp_info = {"error": str(e)}
    finally:
        if conn.State == 1:
            conn.Close()
            
    return comp_info
