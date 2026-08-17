"""
GM Management Backend Bridge Functions
Handles queries for GM OUT (Pending Dispatches).
"""

from bridge.connection import _get_rs

def get_pending_dispatch_bills():
    """
    Fetch all sales vouchers where Bill Status (OF10) is 'Pending'.
    Returns a list of dictionaries with voucher details.
    """
    sql = f"""
        SELECT t1.VchCode, t1.VchNo, t1.Date, t1.VchAmtBaseCur, m.Name AS PartyName, m.NameSL AS HindiName,
               vo.OF7 AS Salesman, vo.OF8 AS BilledBy, vo.OF9 AS PackedBy, vo.OF10 AS BillStatus,
               ma.Mobile
        FROM (((Tran1 t1
        LEFT JOIN Master1 m ON t1.MasterCode1 = m.Code)
        LEFT JOIN VchOtherInfo vo ON t1.VchCode = vo.VchCode)
        LEFT JOIN MasterAddressInfo ma ON m.Code = ma.MasterCode)
        WHERE t1.VchType = 9 
          AND (vo.OF10 = 'Pending' OR vo.OF10 = 'PENDING')
        ORDER BY t1.Date DESC, t1.VchCode DESC
    """
    
    entries = []
    try:
        rst = _get_rs(sql)
        while not rst.EOF:
            vcode = int(rst.Fields("VchCode").Value)
            d_val = rst.Fields("Date").Value
            date_str = d_val.strftime("%d-%m-%Y") if d_val else ""
            
            entries.append({
                "vcode": vcode,
                "vno": str(rst.Fields("VchNo").Value or "").strip(),
                "date": date_str,
                "party_name": str(rst.Fields("PartyName").Value or "").strip(),
                "hindi_name": str(rst.Fields("HindiName").Value or "").strip(),
                "mobile": str(rst.Fields("Mobile").Value or "").strip(),
                "salesman": str(rst.Fields("Salesman").Value or "").strip(),
                "billed_by": str(rst.Fields("BilledBy").Value or "").strip(),
                "packed_by": str(rst.Fields("PackedBy").Value or "").strip(),
                "bill_status": str(rst.Fields("BillStatus").Value or "").strip(),
                "total_amount": float(rst.Fields("VchAmtBaseCur").Value or 0)
            })
            rst.MoveNext()
        rst.Close()
    except Exception as e:
        import sys
        sys.stderr.write(f"Error getting pending dispatch bills: {e}\n")
        
    return entries

def mark_bill_completed(vno):
    """
    Update the Busy database directly to mark the bill status as 'Completed'
    """
    from bridge.connection import g_conn_ref
    conn = g_conn_ref()
    
    # OF10 is the BillStatus column. VchType = 9 is Sales Voucher.
    sql = f"""
        UPDATE VchOtherInfo 
        SET OF10 = 'Complete'
        WHERE VchCode IN (SELECT VchCode FROM Tran1 WHERE VchNo = '{vno}' AND VchType = 9)
    """
    conn.Execute(sql)
    return True
