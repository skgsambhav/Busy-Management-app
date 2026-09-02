"""
Ledger queries - Outstanding bills, party balance, trial balance, full ledger.
"""

from bridge.connection import _get_rs, format_out_date


def get_outstanding_bills(party_code):
    """Get outstanding (unpaid) bills for a party."""
    sql = f"""
        SELECT t3.RefCode, t3.No, t3.Date, t3.DueDate, t3.Value1,
               (SELECT SUM(x.Value1) FROM Tran3 x 
                WHERE x.RefCode = t3.RefCode) AS Balance
        FROM Tran3 t3
        WHERE t3.RecType = 1
          AND t3.Method = 1
          AND t3.MasterCode1 = {party_code}
          AND t3.MasterCode2 = 0
          AND t3.Value1 < 0
        ORDER BY t3.Date
    """
    rst = _get_rs(sql)
    bills = []
    while not rst.EOF:
        bal = rst.Fields("Balance").Value
        if bal is not None and float(bal) < 0:  # Still outstanding
            bills.append({
                "ref_code": int(rst.Fields("RefCode").Value),
                "bill_no": str(rst.Fields("No").Value or "").strip(),
                "date": format_out_date(rst.Fields("Date").Value, ""),
                "due_date": str(rst.Fields("DueDate").Value)[:10] if rst.Fields("DueDate").Value else "",
                "original_amount": abs(float(rst.Fields("Value1").Value or 0)),
                "balance": abs(float(bal))
            })
        rst.MoveNext()
    rst.Close()
    return bills


def get_party_balance(party_code):
    """Get current balance for a party."""
    # Opening balance from Folio1
    sql1 = f"SELECT SUM(D1) AS OpBal FROM Folio1 WHERE MasterCode = {party_code}"
    rst1 = _get_rs(sql1)
    op_bal = float(rst1.Fields("OpBal").Value or 0)
    rst1.Close()
    
    # Transaction balance from Tran2 (RecType=1 = account entries)
    sql2 = f"SELECT SUM(Value1) AS TranBal FROM Tran2 WHERE RecType = 1 AND MasterCode1 = {party_code}"
    rst2 = _get_rs(sql2)
    tran_bal = float(rst2.Fields("TranBal").Value or 0)
    rst2.Close()
    
    total = op_bal + tran_bal
    return {"balance": total, "dr_cr": "Dr" if total < 0 else "Cr", "amount": abs(total)}


def get_trial_balance():
    """Get trial balance for all Sundry Debtors and Creditors."""
    sql = """
        SELECT m.Code, m.Name, m.ParentGrp,
               (SELECT Name FROM Master1 WHERE Code = m.ParentGrp) AS GrpName,
               (SELECT TOP 1 Mobile FROM MasterAddressInfo WHERE MasterCode = m.Code) AS Mobile,
               (SELECT SUM(D1) FROM Folio1 WHERE MasterCode = m.Code) AS OpBal,
               (SELECT SUM(Value1) FROM Tran2 WHERE MasterCode1 = m.Code AND RecType = 1) AS TranBal
        FROM Master1 m
        WHERE m.MasterType = 2
          AND m.ParentGrp IN (
              SELECT Code FROM Master1 
              WHERE MasterType = 1 
              AND (Code IN (116, 117) OR ParentGrp IN (116, 117))
          )
        ORDER BY m.Name
    """
    rst = _get_rs(sql)
    balances = []
    
    while not rst.EOF:
        name = str(rst.Fields("Name").Value or "").strip()
        grp_name = str(rst.Fields("GrpName").Value or "").strip()
        mobile = str(rst.Fields("Mobile").Value or "").strip()
        
        op_bal = rst.Fields("OpBal").Value
        tran_bal = rst.Fields("TranBal").Value
        op_bal = float(op_bal) if op_bal is not None else 0
        tran_bal = float(tran_bal) if tran_bal is not None else 0
        
        total_bal = op_bal + tran_bal
        if total_bal != 0:
            balances.append({
                "code": int(rst.Fields("Code").Value),
                "name": name,
                "group": grp_name,
                "mobile": mobile,
                "balance": total_bal,
                "dr_cr": "Dr" if total_bal < 0 else "Cr",
                "amount": abs(total_bal)
            })
            
        rst.MoveNext()
        
    rst.Close()
    return balances


def get_ledger(party_code):
    """Get full chronological ledger for a party."""
    sql1 = f"SELECT SUM(D1) AS OpBal FROM Folio1 WHERE MasterCode = {party_code}"
    rst1 = _get_rs(sql1)
    op_bal = float(rst1.Fields("OpBal").Value or 0)
    rst1.Close()
    
    # Get mobile, address info
    sql_info = f"SELECT Mobile, TelNo, Address1, Address2, Address3, GSTNo FROM MasterAddressInfo WHERE MasterCode = {party_code}"
    try:
        rst_info = _get_rs(sql_info)
        mobile = str(rst_info.Fields("Mobile").Value or "").strip() if not rst_info.EOF else ""
        tel = str(rst_info.Fields("TelNo").Value or "").strip() if not rst_info.EOF else ""
        addr1 = str(rst_info.Fields("Address1").Value or "").strip() if not rst_info.EOF else ""
        addr2 = str(rst_info.Fields("Address2").Value or "").strip() if not rst_info.EOF else ""
        addr3 = str(rst_info.Fields("Address3").Value or "").strip() if not rst_info.EOF else ""
        gst = str(rst_info.Fields("GSTNo").Value or "").strip() if not rst_info.EOF else ""
        rst_info.Close()
    except:
        mobile = tel = addr1 = addr2 = addr3 = gst = ""
    
    sql = f"""
        SELECT t1.VchType, t1.VchNo, t1.Date, t2.Value1, t2.ShortNar, t2.VchCode
        FROM Tran2 t2
        INNER JOIN Tran1 t1 ON t1.VchCode = t2.VchCode
        WHERE t2.MasterCode1 = {party_code}
        ORDER BY t1.Date, t1.VchCode
    """
    rst = _get_rs(sql)
    transactions = []
    
    while not rst.EOF:
        vch_type = rst.Fields("VchType").Value
        vch_code = rst.Fields("VchCode").Value
        val = float(rst.Fields("Value1").Value or 0)
        
        # Determine opposite account
        opp_sql = f"SELECT TOP 1 m.Name FROM Tran2 t INNER JOIN Master1 m ON t.MasterCode1 = m.Code WHERE t.VchCode = {vch_code} AND t.MasterCode1 <> {party_code} AND m.MasterType IN (1, 2)"
        opp_rs = _get_rs(opp_sql)
        opp_acc = str(opp_rs.Fields("Name").Value).strip() if not opp_rs.EOF else ""
        opp_rs.Close()
        
        transactions.append({
            "vcode": vch_code,
            "date": format_out_date(rst.Fields("Date").Value, ""),
            "type_code": int(vch_type) if vch_type else 0,
            "vch_no": str(rst.Fields("VchNo").Value or "").strip(),
            "amount": val,
            "opp_account": opp_acc,
            "narration": str(rst.Fields("ShortNar").Value or "").strip()
        })
        rst.MoveNext()
        
    rst.Close()
    return {
        "op_bal": op_bal,
        "transactions": transactions,
        "mobile": mobile,
        "tel": tel,
        "address1": addr1,
        "address2": addr2,
        "address3": addr3,
        "gst": gst
    }
