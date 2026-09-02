"""
Sales & Day Book queries - Daily transactions, sales vouchers, voucher details.
"""

from datetime import datetime
from config import VCH_TYPE_NAMES
from bridge.connection import _get_rs, format_out_date, g_conn_ref


def get_daybook(date_str=None):
    """Get Day Book transactions for a given date (default today)."""
    if not date_str:
        date_str = datetime.now().strftime("%Y-%m-%d")
        
    # Format date for MS Access SQL: #YYYY-MM-DD#
    if "/" in date_str:
        parts = date_str.split("/")
        if len(parts) == 3:
            date_str = f"{parts[2]}-{parts[1]:0>2}-{parts[0]:0>2}"
            
    sql = f"""
        SELECT t1.VchCode, t1.VchType, t1.VchNo, t1.Date, t1.MasterCode1 AS HeaderMaster,
               t2.MasterCode1 AS LineMaster, t2.Value1, t2.ShortNar, 
               vo.Narration1 AS VchNarration,
               m.Name AS AccountName, p.Name AS ParentName
        FROM ((((Tran1 t1 
        INNER JOIN Tran2 t2 ON t1.VchCode = t2.VchCode)
        LEFT JOIN Master1 m ON t2.MasterCode1 = m.Code)
        LEFT JOIN Master1 p ON m.ParentGrp = p.Code)
        LEFT JOIN VchOtherInfo vo ON t1.VchCode = vo.VchCode)
        WHERE t1.Date = #{date_str}# AND t2.RecType = 1
        ORDER BY t1.VchType ASC, t1.VchCode ASC, t2.SrNo ASC
    """
    
    rst = _get_rs(sql)
    vouchers = {}
    
    while not rst.EOF:
        vcode = int(rst.Fields("VchCode").Value)
        vtype = int(rst.Fields("VchType").Value)
        vno = str(rst.Fields("VchNo").Value or "").strip()
        vdate = format_out_date(rst.Fields("Date").Value, date_str)
        header_master = int(rst.Fields("HeaderMaster").Value or 0)
        line_master = int(rst.Fields("LineMaster").Value or 0)
        acc_name = str(rst.Fields("AccountName").Value or "").strip()
        grp_name = str(rst.Fields("ParentName").Value or "").strip()
        short_nar = str(rst.Fields("ShortNar").Value or "").strip()
        vch_nar = str(rst.Fields("VchNarration").Value or "").strip()
        val = float(rst.Fields("Value1").Value or 0)
        
        if vcode not in vouchers:
            vouchers[vcode] = {
                "vcode": vcode,
                "vtype": vtype,
                "type_name": VCH_TYPE_NAMES.get(vtype, f"Type {vtype}"),
                "vno": vno,
                "date": vdate,
                "header_master": header_master,
                "vch_narration": vch_nar,
                "lines": []
            }
        vouchers[vcode]["lines"].append({
            "code": line_master,
            "name": acc_name,
            "group": grp_name,
            "val": val,
            "narration": short_nar
        })
        rst.MoveNext()
        
    rst.Close()
    
    entries = []
    for vcode, v in vouchers.items():
        main_line = None
        for l in v["lines"]:
            if l["code"] == v["header_master"] and l["name"]:
                main_line = l
                break
        if not main_line and v["lines"]:
            main_line = max(v["lines"], key=lambda x: abs(x["val"]))
            
        if not main_line:
            continue
            
        acc_name = main_line["name"]
        acc_code = main_line["code"]
        
        narration = v.get("vch_narration", "")
        if not narration:
            narration = main_line.get("narration", "")
        
        total_debit = sum(abs(l["val"]) for l in v["lines"] if l["val"] < 0)
        total_credit = sum(l["val"] for l in v["lines"] if l["val"] > 0)
        
        debit = 0
        credit = 0
        
        if v["vtype"] in (9, 15):  # Sale, Payment
            debit = total_debit
        elif v["vtype"] in (8, 14):  # Purchase, Receipt
            credit = total_credit
        else:
            debit = total_debit
            credit = total_credit
            
        cash_bank_amount = 0
        for l in v["lines"]:
            l_grp_lower = (l["group"] or "").lower()
            l_acc_lower = (l["name"] or "").lower()
            if "cash" in l_grp_lower or "bank" in l_grp_lower or "cash" in l_acc_lower or "bank" in l_acc_lower:
                cash_bank_amount += abs(l["val"])
            
        entries.append({
            "vcode": vcode,
            "vtype": v["vtype"],
            "type": v["type_name"],
            "vno": v["vno"],
            "date": v["date"],
            "account": acc_name,
            "account_code": acc_code,
            "debit": debit,
            "credit": credit,
            "cash_bank": cash_bank_amount,
            "narration": narration
        })
        
    return entries


def get_sales_vouchers(date_str=None):
    """Get all Sales Vouchers (VchType=9) for a given date."""
    if not date_str:
        date_str = datetime.now().strftime("%Y-%m-%d")
        
    if "/" in date_str:
        parts = date_str.split("/")
        if len(parts) == 3:
            date_str = f"{parts[2]}-{parts[1]:0>2}-{parts[0]:0>2}"
            
    sql = f"""
        SELECT t1.VchCode, t1.VchNo, t1.Date, t1.VchAmtBaseCur, m.Name AS PartyName, m.Code AS PartyCode,
               t2.Value1, lm.Name AS LineAccName, lp.Name AS LineGrpName,
               vo.OF7 AS Salesman, vo.OF8 AS BilledBy, vo.OF9 AS PackedBy, vo.OF10 AS BillStatus, c.UserName AS CreatedBy
        FROM ((((((Tran1 t1
        LEFT JOIN Master1 m ON t1.MasterCode1 = m.Code)
        INNER JOIN Tran2 t2 ON t1.VchCode = t2.VchCode)
        LEFT JOIN Master1 lm ON t2.MasterCode1 = lm.Code)
        LEFT JOIN Master1 lp ON lm.ParentGrp = lp.Code)
        LEFT JOIN VchOtherInfo vo ON t1.VchCode = vo.VchCode)
        LEFT JOIN CheckList c ON (t1.VchCode = c.Code AND c.Type = 2 AND c.Action = 1))
        WHERE t1.VchType = 9 AND t1.Date = #{date_str}# AND t2.RecType = 1
        ORDER BY t1.VchCode DESC
    """
    
    rst = _get_rs(sql)
    vouchers = {}
    
    while not rst.EOF:
        vcode = int(rst.Fields("VchCode").Value)
        if vcode not in vouchers:
            vouchers[vcode] = {
                "vcode": vcode,
                "vno": str(rst.Fields("VchNo").Value or "").strip(),
                "date": format_out_date(rst.Fields("Date").Value, date_str),
                "party_name": str(rst.Fields("PartyName").Value or "").strip(),
                "party_code": int(rst.Fields("PartyCode").Value) if rst.Fields("PartyCode").Value else None,
                "busy_user": str(rst.Fields("CreatedBy").Value or "").strip(),
                "salesman": str(rst.Fields("Salesman").Value or "").strip(),
                "billed_by": str(rst.Fields("BilledBy").Value or "").strip(),
                "packed_by": str(rst.Fields("PackedBy").Value or "").strip(),
                "bill_status": str(rst.Fields("BillStatus").Value or "").strip(),
                "net_amount": float(rst.Fields("VchAmtBaseCur").Value or 0),
                "lines": []
            }
            
        val = float(rst.Fields("Value1").Value or 0)
        vouchers[vcode]["lines"].append({
            "val": val,
            "acc": str(rst.Fields("LineAccName").Value or "").strip().lower(),
            "grp": str(rst.Fields("LineGrpName").Value or "").strip().lower()
        })
        rst.MoveNext()
        
    rst.Close()
    
    entries = []
    for vcode, v in vouchers.items():
        net_total = abs(v["net_amount"])
        cash_amount = 0
        for l in v["lines"]:
            if l["val"] < 0:
                if "cash" in l["grp"] or "bank" in l["grp"] or "cash" in l["acc"] or "bank" in l["acc"]:
                    cash_amount += abs(l["val"])
                    
        pending_amount = net_total - cash_amount
        if pending_amount < 0.01: 
            pending_amount = 0
            
        is_cash = (cash_amount >= (net_total - 0.5) and net_total > 0) or ("cash" in v["party_name"].lower())
        if is_cash and pending_amount > 0:
            pending_amount = 0
        
        entries.append({
            "vcode": vcode,
            "vno": v["vno"],
            "date": v["date"],
            "party_name": v["party_name"],
            "party_code": v["party_code"],
            "busy_user": v["busy_user"],
            "salesman": v.get("salesman", ""),
            "billed_by": v["billed_by"],
            "packed_by": v["packed_by"],
            "bill_status": v.get("bill_status", ""),
            "is_cash": is_cash,
            "total_amount": net_total,
            "cash_amount": cash_amount,
            "pending_amount": pending_amount
        })
        
    entries.sort(key=lambda x: x["vcode"], reverse=True)
    return entries


def get_sales_voucher_details(vcode):
    """Get full line-item details for a single Sales Voucher."""
    # 1. Header Info
    sql_header = f"""
        SELECT t1.VchCode, t1.VchNo, t1.Date, t1.MasterCode1, t1.VchAmtBaseCur, m.Name AS PartyName, m.NameSL AS PartyNameSL
        FROM Tran1 t1
        LEFT JOIN Master1 m ON t1.MasterCode1 = m.Code
        WHERE t1.VchCode = {vcode}
    """
    rst_h = _get_rs(sql_header)
    if rst_h.EOF:
        rst_h.Close()
        return {"error": f"Sales Voucher {vcode} not found"}
        
    vno = str(rst_h.Fields("VchNo").Value or "").strip()
    vdate = str(rst_h.Fields("Date").Value)[:10] if rst_h.Fields("Date").Value else ""
    party_name = str(rst_h.Fields("PartyName").Value or "").strip()
    party_name_hi = str(rst_h.Fields("PartyNameSL").Value or "").strip()
    party_code = int(rst_h.Fields("MasterCode1").Value or 0)
    db_net_total = float(rst_h.Fields("VchAmtBaseCur").Value or 0)
    rst_h.Close()
    
    # Fetch Mobile and Address from Master
    mobile = ""
    address = ""
    if party_code:
        sql_addr = f"SELECT Mobile, Address1, Address2 FROM MasterAddressInfo WHERE MasterCode = {party_code}"
        try:
            rst_a = _get_rs(sql_addr)
            if not rst_a.EOF:
                mobile = str(rst_a.Fields("Mobile").Value or "").strip()
                addr1 = str(rst_a.Fields("Address1").Value or "").strip()
                addr2 = str(rst_a.Fields("Address2").Value or "").strip()
                address = f"{addr1}\n{addr2}".strip()
            rst_a.Close()
        except:
            pass
            
    # Try fetching from BillingDet which contains voucher-specific details (e.g. for Cash sales)
    try:
        sql_billdet = f"SELECT PartyName, MobileNo, Address1, Address2 FROM BillingDet WHERE VchCode = {vcode}"
        rst_bd = _get_rs(sql_billdet)
        if not rst_bd.EOF:
            bd_mobile = str(rst_bd.Fields("MobileNo").Value or "").strip()
            bd_party = str(rst_bd.Fields("PartyName").Value or "").strip()
            bd_addr1 = str(rst_bd.Fields("Address1").Value or "").strip()
            bd_addr2 = str(rst_bd.Fields("Address2").Value or "").strip()
            
            if bd_mobile:
                mobile = bd_mobile
            if bd_party and bd_party != "":
                party_name = bd_party
            if bd_addr1 or bd_addr2:
                address = f"{bd_addr1}\n{bd_addr2}".strip()
        rst_bd.Close()
    except:
        pass
    
    # 2. Line Items (RecType = 2)
    sql_items = f"""
        SELECT t2.SrNo, t2.MasterCode1 AS ItemCode, t2.D1 AS Qty, t2.D2 AS Price,
               m.Name AS ItemName, m.NameSL AS ItemNameSL,
               t2.CM3 AS TranUnitCode,
               m.CM1 AS DefaultUnitCode
        FROM Tran2 t2
        LEFT JOIN Master1 m ON t2.MasterCode1 = m.Code
        WHERE t2.VchCode = {vcode} AND t2.RecType = 2
        ORDER BY t2.SrNo ASC
    """
    rst_i = _get_rs(sql_items)
    items = []
    total_qty = 0
    total_amount = 0
    
    sr = 1
    while not rst_i.EOF:
        item_code = int(rst_i.Fields("ItemCode").Value or 0)
        item_name = str(rst_i.Fields("ItemName").Value or "").strip()
        item_name_hi = str(rst_i.Fields("ItemNameSL").Value or "").strip()
        # Per official Busy docs (Inventory Day Book sample query):
        #   Tran2.CM3 = unit actually used in this transaction line
        #   Master1.CM1 = item's default main unit (fallback)
        #   Master1.CM2 = item's alt unit (DO NOT USE for display)
        tran_unit_code = rst_i.Fields("TranUnitCode").Value
        default_unit_code = rst_i.Fields("DefaultUnitCode").Value
        unit_code_val = tran_unit_code if tran_unit_code else default_unit_code
        qty = abs(float(rst_i.Fields("Qty").Value or 0))
        price = float(rst_i.Fields("Price").Value or 0)
        amount = round(qty * price, 2)
        
        unit_name = ""
        unit_name_hi = ""
        if unit_code_val:
            try:
                ucode = int(unit_code_val)
                if ucode > 0:
                    # Use Help1 exactly as Busy's own sample queries do
                    rst_u = _get_rs(f"SELECT NameAlias FROM Help1 WHERE Code = {ucode} AND NameOrAlias = 1")
                    if not rst_u.EOF:
                        unit_name = str(rst_u.Fields("NameAlias").Value or "").strip()
                    rst_u.Close()
                    # Hindi name from Master1
                    rst_u2 = _get_rs(f"SELECT NameSL FROM Master1 WHERE Code = {ucode} AND MasterType = 8")
                    if not rst_u2.EOF:
                        unit_name_hi = str(rst_u2.Fields("NameSL").Value or "").strip()
                    rst_u2.Close()
            except Exception:
                pass
        
        total_qty += qty
        total_amount += amount
        
        items.append({
            "sr_no": sr,
            "item_code": item_code,
            "item_name": item_name,
            "item_name_hi": item_name_hi,
            "unit": unit_name or unit_name_hi,
            "unit_hi": unit_name_hi,
            "unit_en": unit_name,
            "qty": qty,
            "price": price,
            "amount": amount
        })
        sr += 1
        rst_i.MoveNext()
        
    rst_i.Close()
    
    # 3. Bill Sundries (RecType = 3)
    sql_sundries = f"""
        SELECT t2.MasterCode1, m.Name AS AccountName, t2.Value3
        FROM Tran2 t2
        LEFT JOIN Master1 m ON t2.MasterCode1 = m.Code
        WHERE t2.VchCode = {vcode} AND t2.RecType = 3
    """
    rst_s = _get_rs(sql_sundries)
    bill_sundries = []
    
    sr_s = 1
    while not rst_s.EOF:
        mcode = int(rst_s.Fields("MasterCode1").Value or 0)
        s_name = str(rst_s.Fields("AccountName").Value or "").strip()
        s_val = float(rst_s.Fields("Value3").Value or 0)
        
        is_sub = "(-)" in s_name or "discount" in s_name.lower() or "redeem" in s_name.lower() or "less" in s_name.lower()
        if not is_sub and mcode > 0:
            try:
                rs_rec1 = _get_rs(f"SELECT Value1 FROM Tran2 WHERE VchCode={vcode} AND RecType=1 AND MasterCode1={mcode}")
                if not rs_rec1.EOF:
                    val1 = float(rs_rec1.Fields("Value1").Value or 0)
                    if val1 < 0:
                        is_sub = True
                rs_rec1.Close()
            except:
                pass
                
        final_s_val = -abs(s_val) if is_sub else abs(s_val)
        
        bill_sundries.append({
            "sr_no": sr_s,
            "name": s_name,
            "amount": round(final_s_val, 2)
        })
        sr_s += 1
        rst_s.MoveNext()
        
    rst_s.Close()
    
    if db_net_total > 0:
        grand_total = round(db_net_total, 2)
    else:
        grand_total = round(total_amount + sum(s["amount"] for s in bill_sundries), 2)
    
    return {
        "vcode": vcode,
        "vno": vno,
        "date": vdate,
        "party_code": party_code,
        "party_name": party_name,
        "party_name_hi": party_name_hi,
        "mobile": mobile,
        "address": address,
        "series": "Main",
        "sale_type": "L/GST-Exempt",
        "items": items,
        "bill_sundries": bill_sundries,
        "total_qty": total_qty,
        "item_total": round(total_amount, 2),
        "total_amount": grand_total
    }

SALE_VCH_TYPE = 9
SALE_SERIES = 258

def _date_for_xml(date_str):
    if '-' in date_str and len(date_str.split('-')[0]) == 4:
        parts = date_str.split('-')
        return f"{parts[2]}-{parts[1]}-{parts[0]}"
    return date_str

def _get_next_sales_vch_info():
    """Fetch next VchNo for Sales (Type 9)."""
    sql = f"SELECT TOP 1 VchCode, VchNo FROM Tran1 WHERE VchType={SALE_VCH_TYPE} ORDER BY VchCode DESC"
    rst = _get_rs(sql)
    last_vch_no = ""
    if not rst.EOF:
        try:
            last_vch_no = str(rst.Fields('VchNo').Value or "").strip()
        except:
            pass
    rst.Close()
    
    if not last_vch_no:
        return 1, "GM1"
        
    next_num = 1
    prefix = ""
    num_str = ""
    
    for i in range(len(last_vch_no) - 1, -1, -1):
        if last_vch_no[i].isdigit():
            num_str = last_vch_no[i] + num_str
        else:
            prefix = last_vch_no[:i+1]
            break
            
    if num_str:
        next_num = int(num_str) + 1
        
    next_vch_no_str = f"{prefix}{next_num}"
    return next_num, next_vch_no_str

def create_sales_voucher(date_str, customer_code, items, total_amount, narration="", bill_adjustments=None, stpt_name="L/GST-Exempt"):
    import win32com.client
    from config import BFE_PREFIX, USERNAME
    
    g_conn = g_conn_ref()
    
    # 1. Fetch Party Name
    sql_party = f"SELECT Name FROM Master1 WHERE Code = {customer_code}"
    rs_party = _get_rs(sql_party)
    party_name = str(rs_party.Fields('Name').Value or '').strip() if not rs_party.EOF else str(customer_code)
    rs_party.Close()
    
    # 2. Prepare Header Info
    date_xml = _date_for_xml(date_str)
    next_auto_num, next_vch_no_str = _get_next_sales_vch_info()
    
    # 3. Prepare Items XML
    items_xml_parts = []
    sr = 1
    for item in items:
        qty = float(item['qty'])
        price = float(item['price'])
        amt = float(item['amount'])
        icode = item['code']
        
        sql_item = f"SELECT m.Name, u.Name AS UnitName FROM Master1 m LEFT JOIN Master1 u ON u.Code=m.CM1 WHERE m.Code = {icode}"
        rs_item = _get_rs(sql_item)
        iname = str(rs_item.Fields('Name').Value or '').strip() if not rs_item.EOF else str(icode)
        iunit = str(rs_item.Fields('UnitName').Value or '').strip() if not rs_item.EOF else "PCS"
        rs_item.Close()
        
        item_xml = f"""<ItemDetail>
  <Date>{date_xml}</Date>
  <VchType>{SALE_VCH_TYPE}</VchType>
  <VchNo>{next_vch_no_str}</VchNo>
  <SrNo>{sr}</SrNo>
  <ItemName><![CDATA[{iname}]]></ItemName>
  <UnitName>{iunit}</UnitName>
  <Qty>{qty}</Qty>
  <Price>{price}</Price>
  <Amt>{amt}</Amt>
  <NettAmount>{amt}</NettAmount>
  <MC>Main Store</MC>
</ItemDetail>"""
        items_xml_parts.append(item_xml)
        sr += 1
    
    items_xml = "<ItemEntries>" + "".join(items_xml_parts) + "</ItemEntries>"
    
    # 4. Prepare AccEntries (Debtor -Dr, Sales -Cr)
    acc_entries_xml = f"""<AccEntries>
  <AccDetail>
    <Date>{date_xml}</Date>
    <VchType>{SALE_VCH_TYPE}</VchType>
    <VchNo>{next_vch_no_str}</VchNo>
    <SrNo>1</SrNo>
    <AccountName><![CDATA[{party_name}]]></AccountName>
    <AmountType>1</AmountType>
    <AmtMainCur>-{total_amount}</AmtMainCur>
  </AccDetail>
  <AccDetail>
    <Date>{date_xml}</Date>
    <VchType>{SALE_VCH_TYPE}</VchType>
    <VchNo>{next_vch_no_str}</VchNo>
    <SrNo>2</SrNo>
    <AccountName>Sales</AccountName>
    <AmountType>2</AmountType>
    <AmtMainCur>{total_amount}</AmtMainCur>
  </AccDetail>
</AccEntries>"""

    # 5. Prepare PendingBillDetails
    bill_refs_parts = []
    bsr = 1
    
    if bill_adjustments:
        for adj in bill_adjustments:
            rc = adj["ref_code"]
            adj_amt = float(adj["amount"])
            
            sql_ref = f"SELECT No, Date, DueDate FROM Tran3 WHERE RefCode = {rc} AND Method=1"
            rs_ref = _get_rs(sql_ref)
            ref_no = str(rs_ref.Fields("No").Value or "") if not rs_ref.EOF else ""
            raw_date = str(rs_ref.Fields("Date").Value or "")[:10].replace("/", "-") if not rs_ref.EOF else date_xml
            raw_due = str(rs_ref.Fields("DueDate").Value or "")[:10].replace("/", "-") if not rs_ref.EOF else date_xml
            rs_ref.Close()
            
            bill_refs_parts.append(f"""<BillRefs>
  <Method>2</Method>
  <SrNo>{bsr}</SrNo>
  <RefNo>{ref_no}</RefNo>
  <Date>{raw_date}</Date>
  <DueDate>{raw_due}</DueDate>
  <Value1>{adj_amt}</Value1>
  <VchType>{SALE_VCH_TYPE}</VchType>
</BillRefs>""")
            bsr += 1
            
        total_adj = sum(float(a["amount"]) for a in bill_adjustments)
        rem = total_amount - total_adj
        if rem > 0:
            bill_refs_parts.append(f"""<BillRefs>
  <Method>1</Method>
  <SrNo>{bsr}</SrNo>
  <RefNo>{next_vch_no_str}</RefNo>
  <Date>{date_xml}</Date>
  <DueDate>{date_xml}</DueDate>
  <Value1>-{rem}</Value1>
  <VchType>{SALE_VCH_TYPE}</VchType>
</BillRefs>""")
    else:
        bill_refs_parts.append(f"""<BillRefs>
  <Method>1</Method>
  <SrNo>{bsr}</SrNo>
  <RefNo>{next_vch_no_str}</RefNo>
  <Date>{date_xml}</Date>
  <DueDate>{date_xml}</DueDate>
  <Value1>-{total_amount}</Value1>
  <VchType>{SALE_VCH_TYPE}</VchType>
</BillRefs>""")

    bill_refs_combined = "".join(bill_refs_parts)
    pending_bills_xml = f"""<PendingBillDetails>
  <BillDetail>
    <MasterName1><![CDATA[{party_name}]]></MasterName1>
    {bill_refs_combined}
  </BillDetail>
</PendingBillDetails>"""

    # 6. Assemble Full XML
    xml = f"""<?xml version="1.0" encoding="iso8859-1"?>
<Sale>
  <VchSeriesName>Main</VchSeriesName>
  <Date>{date_xml}</Date>
  <VchType>{SALE_VCH_TYPE}</VchType>
  <StockUpdationDate>{date_xml}</StockUpdationDate>
  <VchNo>{next_vch_no_str}</VchNo>
  <AutoVchNo>{next_auto_num}</AutoVchNo>
  <STPTName>{stpt_name}</STPTName>
  <MasterName1><![CDATA[{party_name}]]></MasterName1>
  <MasterName2>Main Store</MasterName2>
  <TranCurName>Rs.</TranCurName>
  <InputType>1</InputType>
  <BillingDetails>
    <PartyName><![CDATA[{party_name}]]></PartyName>
    <PartyNameSL></PartyNameSL>
  </BillingDetails>
  <VchOtherInfoDetails>
    <Narration1><![CDATA[{narration}]]></Narration1>
  </VchOtherInfoDetails>
  {items_xml}
  {acc_entries_xml}
  {pending_bills_xml}
</Sale>"""

    # 7. Save via BFE
    vch = win32com.client.Dispatch(f"{BFE_PREFIX}.CVchDataInv")
    vch.VchType = SALE_VCH_TYPE
    vch.UserName = USERNAME
    vch.SetStateXML(xml, SALE_VCH_TYPE)
    
    err_msg = ""
    ok, err_msg, _ = vch.Save(err_msg)
    
    saved_vch_code = 0
    try:
        saved_vch_code = int(vch.VchCode or 0)
    except:
        pass
        
    if saved_vch_code == 0:
        try:
            sql_check = f"SELECT VchCode FROM Tran1 WHERE VchType={SALE_VCH_TYPE} AND VchNo='{next_vch_no_str}'"
            rs_check = _get_rs(sql_check)
            if not rs_check.EOF:
                saved_vch_code = int(rs_check.Fields("VchCode").Value)
            rs_check.Close()
        except:
            pass
            
    if saved_vch_code > 0:
        return {"success": True, "vch_code": saved_vch_code, "vch_no": next_vch_no_str}
    
    return {"success": False, "error": err_msg}


def find_voucher(vch_no=None, phone=None, date_str=None, hint=None):
    """
    Search for any voucher (Sales=9, Receipt=14, Payment=15, etc.) in Tran1.
    hint can be 'receipt', 'sale', 'payment' or None.
    Returns {"vcode": vcode, "vtype": vtype, "vno": vno} or None.
    """
    vcode = None
    vtype = None
    vno_found = ""

    # 1. Search by VchNo across Tran1
    if vch_no:
        clean_vno = str(vch_no).strip()
        # Direct exact match
        sql = f"SELECT TOP 1 VchCode, VchType, VchNo, Date, VchAmtBaseCur FROM Tran1 WHERE VchNo = '{clean_vno}' ORDER BY VchCode DESC"
        rst = _get_rs(sql)
        if not rst.EOF:
            vcode = int(rst.Fields("VchCode").Value)
            vtype = int(rst.Fields("VchType").Value)
            vno_found = str(rst.Fields("VchNo").Value or "").strip()
        rst.Close()
        
        # If not found, try LIKE match (e.g. if vch_no is "123" and stored as "GM123" or "GMRCPT123")
        if not vcode and len(clean_vno) >= 2:
            sql = f"SELECT TOP 1 VchCode, VchType, VchNo, Date, VchAmtBaseCur FROM Tran1 WHERE (VchNo LIKE '%{clean_vno}%' OR VchNo LIKE '%{clean_vno}') ORDER BY VchCode DESC"
            rst = _get_rs(sql)
            if not rst.EOF:
                vcode = int(rst.Fields("VchCode").Value)
                vtype = int(rst.Fields("VchType").Value)
                vno_found = str(rst.Fields("VchNo").Value or "").strip()
            rst.Close()

    # 2. Search by Phone Number if not found by VchNo
    if not vcode and phone:
        digits = ''.join(c for c in str(phone) if c.isdigit())
        if len(digits) >= 10:
            last10 = digits[-10:]
            sql_party = f"""
                SELECT TOP 1 m.Code FROM Master1 m 
                INNER JOIN MasterAddressInfo mai ON m.Code = mai.MasterCode 
                WHERE mai.Mobile LIKE '%{last10}%' AND m.MasterType = 2
            """
            pcode = None
            try:
                rst_p = _get_rs(sql_party)
                if not rst_p.EOF:
                    pcode = int(rst_p.Fields("Code").Value)
                rst_p.Close()
            except:
                pass
            
            if pcode:
                type_filter = ""
                if hint == "receipt":
                    type_filter = "AND VchType = 14"
                elif hint == "sale":
                    type_filter = "AND VchType = 9"
                elif hint == "payment":
                    type_filter = "AND VchType = 15"
                    
                sql_v = f"SELECT TOP 1 VchCode, VchType, VchNo FROM Tran1 WHERE MasterCode1 = {pcode} {type_filter} ORDER BY VchCode DESC"
                try:
                    rst_v = _get_rs(sql_v)
                    if not rst_v.EOF:
                        vcode = int(rst_v.Fields("VchCode").Value)
                        vtype = int(rst_v.Fields("VchType").Value)
                        vno_found = str(rst_v.Fields("VchNo").Value or "").strip()
                    rst_v.Close()
                except:
                    pass

            # Check BillingDet if still not found
            if not vcode:
                type_filter = ""
                if hint == "receipt":
                    type_filter = "AND t1.VchType = 14"
                elif hint == "sale":
                    type_filter = "AND t1.VchType = 9"
                    
                sql_bd = f"""
                    SELECT TOP 1 t1.VchCode, t1.VchType, t1.VchNo FROM Tran1 t1 
                    INNER JOIN BillingDet bd ON t1.VchCode = bd.VchCode 
                    WHERE bd.MobileNo LIKE '%{last10}%' {type_filter} 
                    ORDER BY t1.VchCode DESC
                """
                try:
                    rst_bd = _get_rs(sql_bd)
                    if not rst_bd.EOF:
                        vcode = int(rst_bd.Fields("VchCode").Value)
                        vtype = int(rst_bd.Fields("VchType").Value)
                        vno_found = str(rst_bd.Fields("VchNo").Value or "").strip()
                    rst_bd.Close()
                except:
                    pass

    # 3. Fallback based on hint
    if not vcode:
        try:
            type_filter = ""
            if hint == "receipt":
                type_filter = "WHERE VchType = 14"
            elif hint == "sale":
                type_filter = "WHERE VchType = 9"
            elif hint == "payment":
                type_filter = "WHERE VchType = 15"
                
            sql_latest = f"SELECT TOP 1 VchCode, VchType, VchNo FROM Tran1 {type_filter} ORDER BY VchCode DESC"
            rst_l = _get_rs(sql_latest)
            if not rst_l.EOF:
                vcode = int(rst_l.Fields("VchCode").Value)
                vtype = int(rst_l.Fields("VchType").Value)
                vno_found = str(rst_l.Fields("VchNo").Value or "").strip()
            rst_l.Close()
        except:
            pass

    return {"vcode": vcode, "vtype": vtype, "vno": vno_found} if vcode else None


def find_sales_voucher(vch_no=None, phone=None, date_str=None):
    """Backwards compatibility wrapper for find_voucher with hint='sale'."""
    res = find_voucher(vch_no=vch_no, phone=phone, date_str=date_str, hint="sale")
    return {"vcode": res["vcode"]} if res else None



