import win32com.client
from bridge.connection import _get_rs, g_conn_ref
from config import BFE_PREFIX, USERNAME, COMP_CODE, DATA_PATH, DB_PASSWORD

PURC_VCH_TYPE = 2

def _date_for_xml(date_str):
    if '-' in date_str and len(date_str.split('-')[0]) == 4:
        parts = date_str.split('-')
        return f"{parts[2]}-{parts[1]}-{parts[0]}"
    return date_str

def _get_next_gst_purc_vch_info():
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

def create_gst_purchase_voucher(date_str, supplier_code, items, total_amount, narration="", bill_adjustments=None, stpt_name="L/GST-ItemWise"):
    """
    Create a GST Purchase voucher via BFE CVchDataInv.
    items: list of dict { code, qty, price, amount (taxable), tax_pct }
    """
    g_conn = g_conn_ref()
    
    # 1. Fetch Party Name & Info
    sql_party = f"SELECT Name, ITPAN, GSTNo, TypeOfDealer FROM Master1 WHERE Code = {supplier_code}"
    rs_party = _get_rs(sql_party)
    party_name = ""
    itpan = ""
    gstno = ""
    tod = "1"
    if not rs_party.EOF:
        party_name = str(rs_party.Fields('Name').Value or '').strip()
        itpan = str(rs_party.Fields('ITPAN').Value or '').strip()
        gstno = str(rs_party.Fields('GSTNo').Value or '').strip()
        tod = str(rs_party.Fields('TypeOfDealer').Value or '1')
    rs_party.Close()
    
    if not party_name:
        party_name = str(supplier_code)
        
    date_xml = _date_for_xml(date_str)
    next_auto_num, next_vch_no_str = _get_next_gst_purc_vch_info()
    
    is_igst = stpt_name.startswith("I/GST")
    
    # Calculate Tax Acc totals
    cgst_total = 0.0
    sgst_total = 0.0
    igst_total = 0.0
    taxable_total = 0.0
    
    items_xml_parts = []
    sr = 1
    for item in items:
        qty = float(item['qty'])
        price = float(item['price'])
        amt = float(item['amount'])  # Note: amt is taxable amount based on frontend setup, wait, in Busy Amt is GROSS (inclusive).
        # We need to map carefully. Let's assume frontend passes `amount` as TAXABLE (price * qty).
        # And gross = taxable + tax
        tax_pct = float(item.get('tax_pct', 0))
        taxable = qty * price
        taxable_total += taxable
        
        tax_val = taxable * (tax_pct / 100.0)
        gross = taxable + tax_val
        
        # Determine STPercent
        if is_igst:
            igst_total += tax_val
            st_percent = tax_pct
            st_amount = tax_val
        else:
            half_tax = tax_val / 2.0
            cgst_total += half_tax
            sgst_total += half_tax
            st_percent = tax_pct / 2.0
            st_amount = half_tax
            
        icode = item['code']
        
        sql_item = f"SELECT m.Name, u.Name AS UnitName FROM Master1 m LEFT JOIN Master1 u ON u.Code=m.CM1 WHERE m.Code = {icode}"
        rs_item = _get_rs(sql_item)
        iname = str(rs_item.Fields('Name').Value or '').strip() if not rs_item.EOF else str(icode)
        iunit = str(rs_item.Fields('UnitName').Value or '').strip() if not rs_item.EOF else "PCS"
        rs_item.Close()
        
        # Busy XML format for GST Item:
        # <Amt> is Gross, <NettAmount> is Taxable
        # <ItemTaxCategory>GST X%</ItemTaxCategory>
        # <STAmount> is either SGST or IGST depending on type, but for L/GST it represents half tax.
        # <STPercent> is half tax %
        # <TaxBeforeSurcharge1> is the other half (CGST)
        # <STPercent1> is the other half %
        tax_cat_name = f"GST {int(tax_pct)}%" if tax_pct.is_integer() else f"GST {tax_pct}%"
        
        item_xml = f"""<ItemDetail>
  <Date>{date_xml}</Date>
  <VchType>{PURC_VCH_TYPE}</VchType>
  <VchNo>{next_vch_no_str}</VchNo>
  <SrNo>{sr}</SrNo>
  <ItemName><![CDATA[{iname}]]></ItemName>
  <UnitName>{iunit}</UnitName>
  <Qty>{qty}</Qty>
  <Price>{price}</Price>
  <Amt>{gross}</Amt>
  <NettAmount>{taxable}</NettAmount>
  <ItemTaxCategory>{tax_cat_name}</ItemTaxCategory>"""

        if is_igst:
            item_xml += f"""
  <STAmount>{st_amount}</STAmount>
  <STPercent>{st_percent}</STPercent>
  <TaxBeforeSurcharge>{st_amount}</TaxBeforeSurcharge>"""
        else:
            item_xml += f"""
  <STAmount>{st_amount}</STAmount>
  <STPercent>{st_percent}</STPercent>
  <TaxBeforeSurcharge1>{st_amount}</TaxBeforeSurcharge1>
  <STPercent1>{st_percent}</STPercent1>
  <TaxBeforeSurcharge>{st_amount}</TaxBeforeSurcharge>"""

        item_xml += f"""
  <MC>Main Store</MC>
</ItemDetail>"""
        items_xml_parts.append(item_xml)
        sr += 1
    
    items_xml = "<ItemEntries>" + "".join(items_xml_parts) + "</ItemEntries>"
    
    # 4. Prepare AccEntries
    # Creditor (-Cr is positive in AmtMainCur for AmountType 2)
    acc_entries_parts = []
    
    # 1. Party (Creditor)
    acc_entries_parts.append(f"""<AccDetail>
  <Date>{date_xml}</Date>
  <VchType>{PURC_VCH_TYPE}</VchType>
  <VchNo>{next_vch_no_str}</VchNo>
  <SrNo>1</SrNo>
  <AccountName><![CDATA[{party_name}]]></AccountName>
  <AmountType>2</AmountType>
  <AmtMainCur>{total_amount}</AmtMainCur>
</AccDetail>""")

    # 2. Purchase (Dr)
    acc_entries_parts.append(f"""<AccDetail>
  <Date>{date_xml}</Date>
  <VchType>{PURC_VCH_TYPE}</VchType>
  <VchNo>{next_vch_no_str}</VchNo>
  <SrNo>2</SrNo>
  <AccountName>Purchase</AccountName>
  <AmountType>1</AmountType>
  <AmtMainCur>-{taxable_total}</AmtMainCur>
</AccDetail>""")

    # 3. Taxes (Dr)
    acc_sr = 3
    if is_igst and igst_total > 0:
        acc_entries_parts.append(f"""<AccDetail>
  <Date>{date_xml}</Date>
  <VchType>{PURC_VCH_TYPE}</VchType>
  <VchNo>{next_vch_no_str}</VchNo>
  <SrNo>{acc_sr}</SrNo>
  <AccountName>IGST Input</AccountName>
  <AmountType>1</AmountType>
  <AmtMainCur>-{igst_total}</AmtMainCur>
</AccDetail>""")
        acc_sr += 1
    elif not is_igst:
        if cgst_total > 0:
            acc_entries_parts.append(f"""<AccDetail>
  <Date>{date_xml}</Date>
  <VchType>{PURC_VCH_TYPE}</VchType>
  <VchNo>{next_vch_no_str}</VchNo>
  <SrNo>{acc_sr}</SrNo>
  <AccountName>CGST Input</AccountName>
  <AmountType>1</AmountType>
  <AmtMainCur>-{cgst_total}</AmtMainCur>
</AccDetail>""")
            acc_sr += 1
        if sgst_total > 0:
            acc_entries_parts.append(f"""<AccDetail>
  <Date>{date_xml}</Date>
  <VchType>{PURC_VCH_TYPE}</VchType>
  <VchNo>{next_vch_no_str}</VchNo>
  <SrNo>{acc_sr}</SrNo>
  <AccountName>SGST Input</AccountName>
  <AmountType>1</AmountType>
  <AmtMainCur>-{sgst_total}</AmtMainCur>
</AccDetail>""")
            acc_sr += 1
            
    acc_entries_xml = "<AccEntries>" + "".join(acc_entries_parts) + "</AccEntries>"

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
  <VchSeriesName>Main</VchSeriesName>
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
    <ITPAN>{itpan}</ITPAN>
    <GSTNo>{gstno}</GSTNo>
    <TypeOfDealer>{tod}</TypeOfDealer>
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
