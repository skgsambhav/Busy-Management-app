"""
Receipt queries - Recent receipts, receipt creation via BFE.
"""

import win32com.client
from config import BFE_PREFIX, USERNAME, RECEIPT, METHOD_ADJUSTMENT
from bridge.connection import _get_rs, format_out_date, g_conn_ref


def get_recent_receipts(limit=20):
    """Get recent receipts."""
    sql = f"""
        SELECT TOP {limit} t1.VchCode, t1.VchNo, t1.Date, t1.VchAmtBaseCur,
               (SELECT TOP 1 m.Name 
                FROM Tran2 t2, Master1 m 
                WHERE t2.VchCode = t1.VchCode 
                  AND t2.RecType = 1 
                  AND t2.Value1 > 0 
                  AND m.Code = t2.MasterCode1) AS PartyName
        FROM Tran1 t1
        WHERE t1.VchType = 14
        ORDER BY t1.VchCode DESC
    """
    rst = _get_rs(sql)
    receipts = []
    while not rst.EOF:
        receipts.append({
            "vch_code": int(rst.Fields("VchCode").Value or 0),
            "vch_no": str(rst.Fields("VchNo").Value or "").strip(),
            "date": format_out_date(rst.Fields("Date").Value, ""),
            "amount": float(rst.Fields("VchAmtBaseCur").Value or 0),
            "party": str(rst.Fields("PartyName").Value or "").strip()
        })
        rst.MoveNext()
    rst.Close()
    return receipts


def _date_for_xml(date_str):
    """Convert DD/MM/YYYY or YYYY-MM-DD to DD-MM-YYYY for BFE XML."""
    parts = date_str.replace("/", "-").split("-")
    if len(parts) == 3 and len(parts[0]) == 4:
        # YYYY-MM-DD to DD-MM-YYYY
        return f"{parts[2]}-{parts[1]}-{parts[0]}"
    return date_str.replace("/", "-")
def _get_next_vch_info():
    """
    Get the next auto voucher number AND formatted VchNo for Receipt series.
    Reads the last VchNo (e.g. 'GMRCPT980') to extract prefix ('GMRCPT').
    Returns (next_auto_num, next_vch_no_str)  e.g. (981, 'GMRCPT981')
    """
    sql = "SELECT TOP 1 VchNo, AutoVchNo FROM Tran1 WHERE VchType=14 AND VchSeriesCode=263 ORDER BY AutoVchNo DESC"
    rst = _get_rs(sql)
    if rst.EOF:
        rst.Close()
        return 1, "GMRCPT1"
    last_vch_no = str(rst.Fields("VchNo").Value or "").strip()
    last_auto = int(rst.Fields("AutoVchNo").Value or 0)
    rst.Close()
    
    next_num = last_auto + 1
    # Extract prefix by removing the trailing numeric portion
    prefix = ""
    for ch in reversed(last_vch_no):
        if ch.isdigit():
            continue
        prefix = last_vch_no[:last_vch_no.rindex(ch) + 1]
        break
    next_vch_no_str = f"{prefix}{next_num}"
    return next_num, next_vch_no_str


def create_receipt(party_code, cash_bank_code, amount, date_str, narration="", bill_adjustments=None):
    """
    Create a receipt voucher via BFE CVchDataAcc using SetStateXML.
    
    party_code: Master1.Code of the debtor
    cash_bank_code: Master1.Code of the cash/bank account
    amount: Receipt amount (positive)
    date_str: "DD/MM/YYYY" format (will be converted to "DD-MM-YYYY" for XML)
    narration: Optional narration text
    bill_adjustments: List of {"ref_code": X, "amount": Y} for bill-by-bill adjustment
    """
    g_conn = g_conn_ref()
    
    # Look up account names from DB
    sql_names = f"SELECT Code, Name FROM Master1 WHERE Code IN ({party_code}, {cash_bank_code})"
    rst_names = _get_rs(sql_names)
    names_map = {}
    while not rst_names.EOF:
        names_map[int(rst_names.Fields('Code').Value)] = str(rst_names.Fields('Name').Value or '').strip()
        rst_names.MoveNext()
    rst_names.Close()
    party_name = names_map.get(party_code, str(party_code))
    cash_bank_name = names_map.get(cash_bank_code, str(cash_bank_code))
    date_xml = _date_for_xml(date_str)
    next_auto_num, next_vch_no_str = _get_next_vch_info()
    
    # --- Build bill reference XML for party line (SrNo=1) ---
    bill_refs_xml = ""
    pending_bills_xml = ""
    ref_info = {}
    
    if bill_adjustments:
        ref_codes_str = ",".join(str(a["ref_code"]) for a in bill_adjustments)
        sql = f"SELECT RefCode, Date, DueDate, No, MasterCode1 FROM Tran3 WHERE RefCode IN ({ref_codes_str}) AND Method=1"
        rst = _get_rs(sql)
        while not rst.EOF:
            rc = int(rst.Fields(0).Value)
            raw_date = str(rst.Fields(1).Value or "")[:10].replace("/", "-")
            raw_due  = str(rst.Fields(2).Value or "")[:10].replace("/", "-")
            bill_no  = str(rst.Fields(3).Value or "")
            mc1      = int(rst.Fields(4).Value or 0)
            ref_info[rc] = {
                "no": bill_no,
                "date": raw_date if raw_date and raw_date != "None" else date_xml,
                "due_date": raw_due if raw_due and raw_due != "None" else date_xml,
                "master_code1": mc1
            }
            rst.MoveNext()
        rst.Close()
        
        sr = 1
        bill_ref_parts = []
        for adj in bill_adjustments:
            rc = adj["ref_code"]
            info = ref_info.get(rc, {})
            ref_no = info.get("no", "")
            ref_date = info.get("date", date_xml).replace("/", "-").replace(" 00:00:00", "")
            due_date = info.get("due_date", date_xml).replace("/", "-").replace(" 00:00:00", "")
            adj_amt = float(adj["amount"])
            
            bill_ref_parts.append(f"""<BillDetails>
    <Method>2</Method>
    <SrNo>{sr}</SrNo>
    <RefNo>{ref_no}</RefNo>
    <Date>{ref_date}</Date>
    <DueDate>{due_date}</DueDate>
    <Value1>{adj_amt}</Value1>
    <VchType>14</VchType>
    <ItemSrNo>1</ItemSrNo>
    <tmpRefCode>{rc}</tmpRefCode>
    <tmpRecType>1</tmpRecType>
    <tmpMasterCode1>{party_code}</tmpMasterCode1>
  </BillDetails>""")
            
        bill_refs_xml = "<BillRefs>" + "".join(bill_ref_parts) + "</BillRefs>"
        pending_bills_xml = ""
    else:
        bill_refs_xml = "<BillRefs />"
        pending_bills_xml = ""
    
    # --- Build the complete XML ---
    narration_xml = ""
    if narration:
        narration_xml = f"<Narration1>{narration}</Narration1>"
    
    xml = f"""<Receipt>
<VchSeriesName>Main</VchSeriesName>
<Date>{date_xml}</Date>
<VchType>14</VchType>
<VchNo>{next_vch_no_str}</VchNo>
<AutoVchNo>{next_auto_num}</AutoVchNo>
<TranCurName>Rs.</TranCurName>
<VchOtherInfoDetails><OFInfo />{narration_xml}</VchOtherInfoDetails>
<AccEntries>
  <AccDetail>
    <Date>{date_xml}</Date>
    <VchType>14</VchType>
    <SrNo>1</SrNo>
    <AccountName>{party_name}</AccountName>
    <AmountType>2</AmountType>
    <AmtMainCur>{amount}</AmtMainCur>
    <CashFlow>{amount}</CashFlow>
    {bill_refs_xml}
  </AccDetail>
  <AccDetail>
    <Date>{date_xml}</Date>
    <VchType>14</VchType>
    <SrNo>2</SrNo>
    <AccountName>{cash_bank_name}</AccountName>
    <AmountType>1</AmountType>
    <AmtMainCur>{amount}</AmtMainCur>
    <BillRefs />
  </AccDetail>
</AccEntries>
{pending_bills_xml}
</Receipt>"""
    
    # --- Save via BFE ---
    vch_acc = win32com.client.Dispatch(f"{BFE_PREFIX}.CVchDataAcc")
    vch_acc.VchType = RECEIPT
    vch_acc.UserName = USERNAME
    vch_acc.SetStateXML(xml, RECEIPT)
    
    err_msg = ""
    try:
        ok, err_msg, _ = vch_acc.Save(err_msg)
    except Exception as e:
        ok = False
        err_msg = str(e)
    
    saved_vch_code = 0
    try:
        saved_vch_code = int(vch_acc.VchCode or 0)
    except:
        pass
        
    # Fallback DB check if COM object failed to return VchCode but might have saved
    if saved_vch_code == 0:
        try:
            sql_check = f"SELECT VchCode FROM Tran1 WHERE VchType={RECEIPT} AND VchNo='{next_vch_no_str}'"
            rs_check = _get_rs(sql_check)
            if not rs_check.EOF:
                saved_vch_code = int(rs_check.Fields("VchCode").Value)
            rs_check.Close()
        except:
            pass
            
    # Busy COM often returns ok=False with some warning even if it successfully saved.
    # If VchCode is found and > 0, it means the voucher was actually saved to the database.
    if saved_vch_code > 0:
        pass # Successfully saved despite false-negative
    elif not ok:
        raise Exception(f"BFE Save failed: {err_msg}")
    if bill_adjustments:
        try:
            sr = 1
            for adj in bill_adjustments:
                rc = adj["ref_code"]
                info = ref_info.get(rc, {})
                ref_no = info.get("no", "")
                ref_date = info.get("date", date_xml)
                due_date_val = info.get("due_date", date_xml)
                adj_amt = float(adj["amount"])
                
                def to_sql_date(d_str):
                    parts = d_str.split('-')
                    if len(parts) == 3:
                        return f"#{parts[2]}-{parts[1]}-{parts[0]}#"
                    return f"#{d_str}#"
                
                sql_date = to_sql_date(ref_date)
                sql_due = to_sql_date(due_date_val)
                safe_ref_no = ref_no.replace("'", "''")
                
                sql_ins = f"INSERT INTO Tran3 (VchCode, VchType, MasterCode1, RefCode, Method, [No], [Date], DueDate, Value1, RecType, SrNo, Status, Type, ItemSrNo, MfgDate) VALUES ({saved_vch_code}, {RECEIPT}, {party_code}, {rc}, {METHOD_ADJUSTMENT}, '{safe_ref_no}', {sql_date}, {sql_due}, {adj_amt}, 1, {sr}, 1, 2, 1, #1899-12-30#)"
                g_conn.Execute(sql_ins)
                sr += 1
        except Exception as e:
            raise Exception(f"BFE Save succeeded but Tran3 update failed: {e}")
    
    # Retrieve final VchNo from DB
    sql2 = f"SELECT VchNo FROM Tran1 WHERE VchCode={saved_vch_code}"
    rst2 = _get_rs(sql2)
    saved_vch_no = ""
    if not rst2.EOF:
        saved_vch_no = str(rst2.Fields("VchNo").Value or "").strip()
    rst2.Close()
    
    if not saved_vch_no:
        saved_vch_no = next_vch_no_str # Fallback
    
    return {
        "success": True,
        "vch_code": saved_vch_code,
        "vch_no": saved_vch_no,
        "auto_vch_no": next_auto_num
    }

def get_receipt_voucher_details(vcode):
    """Get line-item and reference details for a single Receipt Voucher."""
    # 1. Header Info
    sql_header = f"""
        SELECT t1.VchCode, t1.VchNo, t1.Date, t1.VchAmtBaseCur, t1.Narration
        FROM Tran1 t1
        WHERE t1.VchCode = {vcode}
    """
    rst_h = _get_rs(sql_header)
    if rst_h.EOF:
        rst_h.Close()
        return {"error": f"Receipt Voucher {vcode} not found"}
        
    vno = str(rst_h.Fields("VchNo").Value or "").strip()
    d_val = rst_h.Fields("Date").Value
    vdate = d_val.strftime("%d-%m-%Y") if d_val else ""
    amount = float(rst_h.Fields("VchAmtBaseCur").Value or 0)
    narration = str(rst_h.Fields("Narration").Value or "").strip()
    rst_h.Close()
    
    # 2. Party Name and Cash/Bank Name
    sql_ledgers = f"""
        SELECT t2.Value1, m.Name AS AccountName
        FROM Tran2 t2
        INNER JOIN Master1 m ON t2.MasterCode1 = m.Code
        WHERE t2.VchCode = {vcode} AND t2.RecType = 1
    """
    rst_l = _get_rs(sql_ledgers)
    party_name = ""
    cash_bank_name = ""
    while not rst_l.EOF:
        val = float(rst_l.Fields("Value1").Value or 0)
        acc_name = str(rst_l.Fields("AccountName").Value or "").strip()
        if val > 0:
            party_name = acc_name
        elif val < 0:
            cash_bank_name = acc_name
        rst_l.MoveNext()
    rst_l.Close()
    
    # 3. Bill Adjustments
    sql_adj = f"""
        SELECT No, Value1 FROM Tran3 WHERE VchCode = {vcode}
    """
    rst_a = _get_rs(sql_adj)
    adjustments = []
    while not rst_a.EOF:
        adjustments.append({
            "ref_no": str(rst_a.Fields("No").Value or "").strip(),
            "amount": abs(float(rst_a.Fields("Value1").Value or 0))
        })
        rst_a.MoveNext()
    rst_a.Close()
    
    return {
        "vchno": vno,
        "date": vdate,
        "amount": amount,
        "narration": narration,
        "party_name": party_name,
        "cash_bank_name": cash_bank_name,
        "adjustments": adjustments
    }
