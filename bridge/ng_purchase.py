import datetime
import win32com.client
from bridge.connection import _get_rs, g_conn_ref
from config import BFE_PREFIX, USERNAME, COMP_CODE, DATA_PATH, DB_PASSWORD

PURC_VCH_TYPE = 8
PURC_SERIES = 251

def _date_for_xml(date_str):
    if '-' in date_str and len(date_str.split('-')[0]) == 4:
        parts = date_str.split('-')
        return f"{parts[2]}-{parts[1]}-{parts[0]}"
    return date_str

def _get_next_purc_vch_info():
    """Fetch next AutoVchNo and VchNo for Purchase (Type 2)."""
    sql = f"SELECT TOP 1 AutoVchNo, VchNo FROM Tran1 WHERE VchType={PURC_VCH_TYPE} ORDER BY AutoVchNo DESC"
    rst = _get_rs(sql)
    last_auto = 0
    last_vch_no = ""
    if not rst.EOF:
        try:
            last_auto = int(rst.Fields('AutoVchNo').Value or 0)
            last_vch_no = str(rst.Fields('VchNo').Value or "").strip()
        except:
            pass
    rst.Close()
    
    if last_auto == 0:
        return 1, "P1"
        
    next_num = last_auto + 1
    prefix = ""
    for ch in reversed(last_vch_no):
        if ch.isdigit():
            continue
        prefix = last_vch_no[:last_vch_no.rindex(ch) + 1]
        break
    next_vch_no_str = f"{prefix}{next_num}"
    return next_num, next_vch_no_str

def create_purchase_voucher(date_str, supplier_code, items, total_amount, narration="", bill_adjustments=None, stpt_name="L/GST-Exempt"):
    """
    Create a Purchase voucher via BFE CVchDataInv using SetStateXML.
    """
    g_conn = g_conn_ref()
    
    # 1. Fetch Party Name
    sql_party = f"SELECT Name FROM Master1 WHERE Code = {supplier_code}"
    rs_party = _get_rs(sql_party)
    party_name = str(rs_party.Fields('Name').Value or '').strip() if not rs_party.EOF else str(supplier_code)
    rs_party.Close()
    
    # 2. Prepare Header Info
    date_xml = _date_for_xml(date_str)
    next_auto_num, next_vch_no_str = _get_next_purc_vch_info()
    
    # 3. Prepare Items XML
    items_xml_parts = []
    sr = 1
    for item in items:
        qty = float(item['qty'])
        price = float(item['price'])
        amt = float(item['amount'])
        icode = item['code']
        
        # Fetch item name & unit name
        sql_item = f"SELECT m.Name, u.Name AS UnitName FROM Master1 m LEFT JOIN Master1 u ON u.Code=m.CM1 WHERE m.Code = {icode}"
        rs_item = _get_rs(sql_item)
        iname = str(rs_item.Fields('Name').Value or '').strip() if not rs_item.EOF else str(icode)
        iunit = str(rs_item.Fields('UnitName').Value or '').strip() if not rs_item.EOF else "PCS"
        rs_item.Close()
        
        item_xml = f"""<ItemDetail>
  <Date>{date_xml}</Date>
  <VchType>{PURC_VCH_TYPE}</VchType>
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
    
    # 4. Prepare AccEntries (Creditor -Cr, Purchase -Dr)
    acc_entries_xml = f"""<AccEntries>
  <AccDetail>
    <Date>{date_xml}</Date>
    <VchType>{PURC_VCH_TYPE}</VchType>
    <VchNo>{next_vch_no_str}</VchNo>
    <SrNo>1</SrNo>
    <AccountName><![CDATA[{party_name}]]></AccountName>
    <AmountType>2</AmountType>
    <AmtMainCur>{total_amount}</AmtMainCur>
  </AccDetail>
  <AccDetail>
    <Date>{date_xml}</Date>
    <VchType>{PURC_VCH_TYPE}</VchType>
    <VchNo>{next_vch_no_str}</VchNo>
    <SrNo>2</SrNo>
    <AccountName>Purchase</AccountName>
    <AmountType>1</AmountType>
    <AmtMainCur>-{total_amount}</AmtMainCur>
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
  <Value1>-{adj_amt}</Value1>
  <VchType>{PURC_VCH_TYPE}</VchType>
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
  <Value1>{rem}</Value1>
  <VchType>{PURC_VCH_TYPE}</VchType>
</BillRefs>""")
    else:
        bill_refs_parts.append(f"""<BillRefs>
  <Method>1</Method>
  <SrNo>{bsr}</SrNo>
  <RefNo>{next_vch_no_str}</RefNo>
  <Date>{date_xml}</Date>
  <DueDate>{date_xml}</DueDate>
  <Value1>{total_amount}</Value1>
  <VchType>{PURC_VCH_TYPE}</VchType>
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
<Purchase>
  <VchSeriesName>08Main</VchSeriesName>
  <Date>{date_xml}</Date>
  <VchType>{PURC_VCH_TYPE}</VchType>
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
</Purchase>"""

    # 7. Save via BFE
    vch = win32com.client.Dispatch(f"{BFE_PREFIX}.CVchDataInv")
    vch.VchType = PURC_VCH_TYPE
    vch.UserName = USERNAME
    vch.SetStateXML(xml, PURC_VCH_TYPE)
    
    err_msg = ""
    ok, err_msg, _ = vch.Save(err_msg)
    
    saved_vch_code = 0
    try:
        saved_vch_code = int(vch.VchCode or 0)
    except:
        pass
        
    if saved_vch_code == 0:
        try:
            sql_check = f"SELECT VchCode FROM Tran1 WHERE VchType={PURC_VCH_TYPE} AND VchNo='{next_vch_no_str}'"
            rs_check = _get_rs(sql_check)
            if not rs_check.EOF:
                saved_vch_code = int(rs_check.Fields("VchCode").Value)
            rs_check.Close()
        except:
            pass
            
    if saved_vch_code > 0:
        return {"success": True, "vch_code": saved_vch_code, "vch_no": next_vch_no_str}
    
    return {"success": False, "error": err_msg}
