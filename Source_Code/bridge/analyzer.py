"""
Scrutiny Analyzer - Duplicate receipt detection.
"""

from config import SUNDRY_DEBTORS_CODE, SUNDRY_CREDITORS_CODE
from bridge.connection import _get_rs, format_out_date
import datetime
from collections import defaultdict
from itertools import combinations


def get_duplicate_receipts(days_gap=3, days_limit=0):
    """Detect double entries for receipts based on party, amount, and date proximity."""
    
    date_filter = ""
    if days_limit:
        start_date = datetime.datetime.now() - datetime.timedelta(days=int(days_limit) - 1)
        date_filter = f" AND t1.Date >= #{start_date.strftime('%Y-%m-%d')}# "
    
    # 1. Get all valid Debtor/Creditor group codes
    sql_grp = f"""
        SELECT Code FROM Master1 
        WHERE MasterType = 1 
        AND (Code IN ({SUNDRY_DEBTORS_CODE}, {SUNDRY_CREDITORS_CODE}) 
          OR ParentGrp IN ({SUNDRY_DEBTORS_CODE}, {SUNDRY_CREDITORS_CODE}))
    """
    rs_grp = _get_rs(sql_grp)
    valid_groups = {SUNDRY_DEBTORS_CODE, SUNDRY_CREDITORS_CODE}
    while not rs_grp.EOF:
        valid_groups.add(int(rs_grp.Fields("Code").Value))
        rs_grp.MoveNext()
    rs_grp.Close()

    # 2. Fetch receipts
    sql = f"""
        SELECT t1.VchCode, t1.VchNo, t1.Date, t1.VchAmtBaseCur, m.Name AS PartyName, t2.Value1, m.ParentGrp
        FROM (Tran1 t1
        INNER JOIN Tran2 t2 ON t1.VchCode = t2.VchCode)
        LEFT JOIN Master1 m ON t2.MasterCode1 = m.Code
        WHERE t1.VchType = 14 AND t2.RecType = 1 AND t2.Value1 > 0
          {date_filter}
        ORDER BY t1.Date DESC, t1.VchCode DESC
    """
    
    rst = _get_rs(sql)
    receipts = []
    
    while not rst.EOF:
        grp = int(rst.Fields("ParentGrp").Value or 0)
        if grp in valid_groups:
            date_val = rst.Fields("Date").Value
            if date_val:
                receipts.append({
                    "vcode": int(rst.Fields("VchCode").Value),
                    "vno": str(rst.Fields("VchNo").Value or "").strip(),
                    "date": date_val,
                    "party": str(rst.Fields("PartyName").Value or "").strip(),
                    "amount": abs(float(rst.Fields("Value1").Value or 0))
                })
        rst.MoveNext()
        
    rst.Close()
    
    groups = {}
    for r in receipts:
        if not r["party"] or r["party"].upper() == ".CASH":
            continue
        key = (r["party"], round(r["amount"], 2))
        if key not in groups:
            groups[key] = []
        groups[key].append(r)
        
    duplicates = []
    seen_pairs = set()
    for (party, amount), items in groups.items():
        if len(items) > 1:
            items.sort(key=lambda x: x["date"])
            for i in range(len(items) - 1):
                r1 = items[i]
                r2 = items[i+1]
                diff = (r2["date"] - r1["date"]).days
                if diff <= days_gap:
                    # Dedup: avoid reporting same pair twice (e.g. when 3 identical receipts exist)
                    pair_key = (r1["vcode"], r2["vcode"])
                    if pair_key in seen_pairs:
                        continue
                    seen_pairs.add(pair_key)
                    duplicates.append({
                        "party": party,
                        "amount": amount,
                        "vch1": r1["vno"],
                        "date1": format_out_date(r1["date"], ""),
                        "vch2": r2["vno"],
                        "date2": format_out_date(r2["date"], ""),
                        "days_diff": diff,
                        "_sort_dt": r2["date"]  # keep raw datetime for sorting
                    })
                    
    # Sort by actual datetime descending (string sort on formatted dates is WRONG)
    duplicates.sort(key=lambda x: x.pop("_sort_dt"), reverse=True)
    return duplicates

def get_sales_item_duplicates(days=0):
    """Find items in the same sales voucher with identical Name, Qty, and Rate."""
    date_filter = ""
    if days:
        start_date = datetime.datetime.now() - datetime.timedelta(days=int(days) - 1)
        date_filter = f" AND t1.Date >= #{start_date.strftime('%Y-%m-%d')}# "
        
    sql = f"""
        SELECT t1.VchCode, t1.VchNo, t1.Date, m.Name as ItemName, t2.MasterCode1, t2.D1 as Qty, t2.D2 as Rate, t2.Value3 as Amt, COUNT(*) as DupCount
        FROM (Tran1 t1 
        INNER JOIN Tran2 t2 ON t1.VchCode = t2.VchCode)
        INNER JOIN Master1 m ON t2.MasterCode1 = m.Code
        WHERE t1.VchType = 9 AND t2.RecType = 2
          AND (t2.D2 <> 0 OR t2.Value3 <> 0)
          {date_filter}
        GROUP BY t1.VchCode, t1.VchNo, t1.Date, m.Name, t2.MasterCode1, t2.D1, t2.D2, t2.Value3
        HAVING COUNT(*) > 1
        ORDER BY t1.Date DESC
    """
    dupes_dict = {}
    dupes_list = []
    try:
        rs = _get_rs(sql)
        vch_codes = set()
        while not rs.EOF:
            vcode = int(rs.Fields("VchCode").Value)
            mcode = int(rs.Fields("MasterCode1").Value)
            qty = float(rs.Fields("Qty").Value or 0)
            rate = float(rs.Fields("Rate").Value or 0)
            amt = float(rs.Fields("Amt").Value or 0)
            
            key = (vcode, mcode, qty, rate, amt)
            
            vchno = str(rs.Fields("VchNo").Value or "").strip()
            dt = rs.Fields("Date").Value
            date_str = dt.strftime("%d-%m-%Y") if dt else ""
            item_name = str(rs.Fields("ItemName").Value or "")
            dup_count = int(rs.Fields("DupCount").Value or 0)
            
            d_obj = {
                "vchno": vchno,
                "date": date_str,
                "item_name": item_name,
                "qty": qty,
                "rate": rate,
                "amt": amt,
                "dup_count": dup_count,
                "sr_nos": []
            }
            dupes_dict[key] = d_obj
            dupes_list.append(d_obj)
            vch_codes.add(vcode)
            
            rs.MoveNext()
        rs.Close()
        
        if vch_codes:
            # Query the SrNos for these VchCodes
            vch_in = ",".join(map(str, vch_codes))
            # Bug fix: MUST include RecType = 2 to only look at item lines
            sql2 = f"SELECT VchCode, MasterCode1, D1, D2, Value3, SrNo FROM Tran2 WHERE VchCode IN ({vch_in}) AND RecType = 2 ORDER BY VchCode, SrNo"
            rs2 = _get_rs(sql2)
            while not rs2.EOF:
                vc = int(rs2.Fields("VchCode").Value)
                mc = int(rs2.Fields("MasterCode1").Value)
                q = float(rs2.Fields("D1").Value or 0)
                r = float(rs2.Fields("D2").Value or 0)
                a = float(rs2.Fields("Value3").Value or 0)
                sr = int(rs2.Fields("SrNo").Value)
                
                key = (vc, mc, q, r, a)
                if key in dupes_dict:
                    dupes_dict[key]["sr_nos"].append(sr)
                rs2.MoveNext()
            rs2.Close()
            
            # Format the sr_nos as a string for UI
            for d in dupes_list:
                d["sr_nos"].sort()
                d["sr_nos_str"] = ", ".join(map(str, d["sr_nos"]))
                
    except Exception as e:
        print(f"Error getting sales item duplicates: {e}")
    return dupes_list

def get_sales_qty_amt_discrepancies(days=0):
    """Find sales voucher line items where Qty is entered but Amt is 0, or Amt is entered but Qty is 0.
    
    Conditions checked:
      - Qty present (D1 != 0) but Amount (Value3) is 0 → likely forgot to enter amount
      - Amount present (Value3 != 0) but Qty (D1) is 0 → likely free/gifted or data entry error  
      - Rate present (D2 != 0) but both Qty and Amount are 0 → orphan rate entry
    Note: We skip rows where ALL of D1, D2, Value3 are 0 (completely blank lines).
    """
    date_filter = ""
    if days:
        start_date = datetime.datetime.now() - datetime.timedelta(days=int(days) - 1)
        date_filter = f" AND t1.Date >= #{start_date.strftime('%Y-%m-%d')}# "
        
    sql = f"""
        SELECT t1.VchCode, t1.VchNo, t1.Date, m.Name as ItemName, t2.SrNo, t2.D1 as Qty, t2.D2 as Rate, t2.Value3 as Amt
        FROM (Tran1 t1 
        INNER JOIN Tran2 t2 ON t1.VchCode = t2.VchCode)
        INNER JOIN Master1 m ON t2.MasterCode1 = m.Code
        WHERE t1.VchType = 9 AND t2.RecType = 2
          AND (
            (t2.D1 <> 0 AND t2.Value3 = 0)
            OR (t2.D1 = 0 AND t2.Value3 <> 0)
            OR (t2.D1 = 0 AND t2.Value3 = 0 AND t2.D2 <> 0)
          )
          {date_filter}
        ORDER BY t1.Date DESC, t1.VchNo, t2.SrNo
    """
    mismatches = []
    try:
        rs = _get_rs(sql)
        while not rs.EOF:
            vchno = str(rs.Fields("VchNo").Value or "").strip()
            dt = rs.Fields("Date").Value
            date_str = dt.strftime("%d-%m-%Y") if dt else ""
            item_name = str(rs.Fields("ItemName").Value or "")
            sr_no = int(rs.Fields("SrNo").Value or 0)
            qty = float(rs.Fields("Qty").Value or 0)
            rate = float(rs.Fields("Rate").Value or 0)
            amt = float(rs.Fields("Amt").Value or 0)
            
            if qty != 0 and amt == 0:
                issue_type = "Qty Present, Amount Missing"
            elif qty == 0 and amt != 0:
                issue_type = "Amount Present, Qty Missing"
            elif qty == 0 and amt == 0 and rate != 0:
                issue_type = "Rate Present, Qty/Amt Missing"
            else:
                issue_type = "Discrepancy"
                
            mismatches.append({
                "vchno": vchno,
                "date": date_str,
                "item_name": item_name,
                "sr_no": sr_no,
                "qty": qty,
                "rate": rate,
                "amt": amt,
                "issue_type": issue_type
            })
            rs.MoveNext()
        rs.Close()
    except Exception as e:
        print(f"Error getting sales qty/amt mismatches: {e}")
    return mismatches


def get_cross_voucher_duplicates(months_back=0, days=0):
    """Find pairs of sales vouchers on the same day that share identical items (Name, Qty, Rate).
    
    Flags a pair if:
      - At least 3 items in common, AND
      - The overlapping items are >= 50% of the SMALLER voucher's item count
    This catches partial duplicates (e.g. GM4043 vs GM4046 with 15/20 common items).
    """
    
    # 1. Get latest sales date
    latest_dt_rs = _get_rs("SELECT MAX(Date) as MaxDate FROM Tran1 WHERE VchType = 9")
    if not latest_dt_rs.EOF and latest_dt_rs.Fields("MaxDate").Value:
        max_date = latest_dt_rs.Fields("MaxDate").Value
    else:
        max_date = datetime.date.today()
    latest_dt_rs.Close()
    
    if isinstance(max_date, datetime.datetime):
        max_date = max_date.date()
        
    # 2. Get earliest sales date to check has_more
    earliest_dt_rs = _get_rs("SELECT MIN(Date) as MinDate FROM Tran1 WHERE VchType = 9")
    if not earliest_dt_rs.EOF and earliest_dt_rs.Fields("MinDate").Value:
        min_date = earliest_dt_rs.Fields("MinDate").Value
    else:
        min_date = datetime.date(2000, 1, 1)
    earliest_dt_rs.Close()
    
    if isinstance(min_date, datetime.datetime):
        min_date = min_date.date()

    if days:
        start_date = datetime.datetime.now() - datetime.timedelta(days=int(days) - 1)
        end_date = datetime.datetime.now()
        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")
        has_more = False

    else:
        # 3. Calculate target month start & end dates
        year = max_date.year
        month = max_date.month
        
        for _ in range(months_back):
            month -= 1
            if month == 0:
                month = 12
                year -= 1
                
        start_date = datetime.date(year, month, 1)
        if month == 12:
            end_date = datetime.date(year, 12, 31)
        else:
            end_date = datetime.date(year, month + 1, 1) - datetime.timedelta(days=1)
            
        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")
        has_more = start_date > min_date
    
    # Also fetch party (MasterCode1 from Tran1) to include in the voucher metadata
    sql = f"""
        SELECT t1.VchCode, t1.VchNo, t1.Date,
               mp.Name as PartyName,
               mi.Name as ItemName,
               t2.D1 as Qty, t2.D2 as Rate
        FROM ((Tran1 t1 
        INNER JOIN Tran2 t2 ON t1.VchCode = t2.VchCode)
        INNER JOIN Master1 mi ON t2.MasterCode1 = mi.Code)
        LEFT JOIN Master1 mp ON t1.MasterCode1 = mp.Code
        WHERE t1.VchType = 9 AND t2.RecType = 2
          AND (t2.D2 <> 0 OR t2.Value3 <> 0)
          AND t1.Date >= #{start_str}# AND t1.Date <= #{end_str}#
        ORDER BY t1.Date DESC, t1.VchCode
    """
    
    day_vouchers = defaultdict(dict)
    try:
        rs = _get_rs(sql)
        while not rs.EOF:
            vcode = int(rs.Fields("VchCode").Value)
            vchno = str(rs.Fields("VchNo").Value or "").strip()
            dt = rs.Fields("Date").Value
            if not dt:
                rs.MoveNext()
                continue
                
            date_str = dt.strftime("%d-%m-%Y")
            party_name = str(rs.Fields("PartyName").Value or "").strip()
            item_name = str(rs.Fields("ItemName").Value or "")
            qty = float(rs.Fields("Qty").Value or 0)
            rate = float(rs.Fields("Rate").Value or 0)
            
            item_tuple = (item_name, qty, rate)
            
            if vcode not in day_vouchers[date_str]:
                day_vouchers[date_str][vcode] = {
                    "vchno": vchno,
                    "party": party_name,
                    "items": set()
                }
                
            day_vouchers[date_str][vcode]["items"].add(item_tuple)
            
            rs.MoveNext()
        rs.Close()
    except Exception as e:
        print(f"Error getting cross voucher duplicates: {e}")
        return {"suspects": [], "has_more": False}
        
    suspects = []
    
    # Thresholds — FIXED: was requiring 100% subset (intersection == len(items1) or items2)
    # Now using: >= 3 common items AND >= 50% overlap ratio of smaller voucher
    MIN_MATCH_COUNT = 3
    MIN_OVERLAP_RATIO = 0.50  # 50% of the smaller voucher must match
    
    for date_str, vouchers in day_vouchers.items():
        vcode_list = list(vouchers.keys())
        if len(vcode_list) < 2:
            continue
            
        for v1, v2 in combinations(vcode_list, 2):
            items1 = vouchers[v1]["items"]
            items2 = vouchers[v2]["items"]
            
            intersection = items1.intersection(items2)
            match_count = len(intersection)
            
            if match_count == 0:
                continue
            
            # Overlap ratio based on the smaller voucher
            smaller_size = min(len(items1), len(items2))
            overlap_ratio = match_count / smaller_size if smaller_size > 0 else 0
            
            # Flag if >= MIN_MATCH_COUNT items match AND overlap >= MIN_OVERLAP_RATIO of smaller voucher
            if match_count >= MIN_MATCH_COUNT and overlap_ratio >= MIN_OVERLAP_RATIO:
                match_details = [{"name": i[0], "qty": i[1], "rate": i[2]} for i in sorted(intersection)]
                overlap_pct = round(overlap_ratio * 100, 1)
                
                suspects.append({
                    "date": date_str,
                    "vch1": vouchers[v1]["vchno"],
                    "vch2": vouchers[v2]["vchno"],
                    "party1": vouchers[v1]["party"],
                    "party2": vouchers[v2]["party"],
                    "vch1_len": len(items1),
                    "vch2_len": len(items2),
                    "match_count": match_count,
                    "overlap_pct": overlap_pct,
                    "matches": match_details
                })
                
    suspects.sort(key=lambda x: (datetime.datetime.strptime(x["date"], "%d-%m-%Y"), -x["match_count"]), reverse=True)
    return {"suspects": suspects, "has_more": has_more}


def get_performance_metrics(from_date=None, to_date=None):
    """Get aggregated daily sales, receipts, payments, cash, and bank inflow between dates. Excludes empty Tuesdays from timeline."""
    from datetime import datetime, timedelta
    
    if not to_date:
        end_date = datetime.now()
    else:
        end_date = datetime.strptime(to_date, "%Y-%m-%d")
        
    if not from_date:
        start_date = end_date - timedelta(days=30)
    else:
        start_date = datetime.strptime(from_date, "%Y-%m-%d")
        
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")
    
    # Get Cash Code
    cash_code = 1
    try:
        cash_rs = _get_rs("SELECT Code FROM Master1 WHERE Name = '.CASH' OR Name = 'Cash' OR Name = 'CASH'")
        if not cash_rs.EOF:
            cash_code = int(cash_rs.Fields("Code").Value)
        cash_rs.Close()
    except:
        pass

    # 1. Get Sales (VchType 9)
    sql_sales = f"""
        SELECT t1.Date, 
               SUM(t1.VchAmtBaseCur) as TotalSales,
               SUM(IIF(t1.MasterCode1 <> {cash_code}, t1.VchAmtBaseCur, 0)) as CreditSales
        FROM Tran1 t1
        WHERE t1.VchType = 9 
        AND t1.Date >= #{start_str}# AND t1.Date <= #{end_str}#
        GROUP BY t1.Date
    """
    sales_data = {}
    credit_sales_data = {}
    try:
        rs = _get_rs(sql_sales)
        while not rs.EOF:
            d_val = rs.Fields("Date").Value
            if d_val:
                ds_key = d_val.strftime("%Y-%m-%d")
                sales_data[ds_key] = float(rs.Fields("TotalSales").Value or 0)
                credit_sales_data[ds_key] = float(rs.Fields("CreditSales").Value or 0)
            rs.MoveNext()
        rs.Close()
    except:
        pass

    # 2. Get Receipts (VchType 14)
    sql_rect = f"""
        SELECT t1.Date, SUM(t1.VchAmtBaseCur) as TotalReceipts, COUNT(t1.VchCode) as CountReceipts
        FROM Tran1 t1
        WHERE t1.VchType = 14 
        AND t1.Date >= #{start_str}# AND t1.Date <= #{end_str}#
        GROUP BY t1.Date
    """
    rect_data = {}
    rect_count = {}
    try:
        rs = _get_rs(sql_rect)
        while not rs.EOF:
            d_val = rs.Fields("Date").Value
            if d_val:
                date_key = d_val.strftime("%Y-%m-%d")
                rect_data[date_key] = float(rs.Fields("TotalReceipts").Value or 0)
                rect_count[date_key] = int(rs.Fields("CountReceipts").Value or 0)
            rs.MoveNext()
        rs.Close()
    except:
        pass

    # 3. Get Payments (VchType 3)
    sql_pymt = f"""
        SELECT t1.Date, SUM(t1.VchAmtBaseCur) as TotalPayments
        FROM Tran1 t1
        WHERE t1.VchType = 3 
        AND t1.Date >= #{start_str}# AND t1.Date <= #{end_str}#
        GROUP BY t1.Date
    """
    pymt_data = {}
    try:
        rs = _get_rs(sql_pymt)
        while not rs.EOF:
            d_val = rs.Fields("Date").Value
            if d_val:
                pymt_data[d_val.strftime("%Y-%m-%d")] = float(rs.Fields("TotalPayments").Value or 0)
            rs.MoveNext()
        rs.Close()
    except:
        pass

    # 4. Get Cash vs Bank/PYMT Receipts Breakdown (Inflow)
    sql_cash_bank = f"""
        SELECT t1.Date, m.ParentGrp, SUM(t2.Value1) as Amt
        FROM (Tran1 t1 
          INNER JOIN Tran2 t2 ON t1.VchCode = t2.VchCode) 
          INNER JOIN Master1 m ON t2.MasterCode1 = m.Code
        WHERE m.ParentGrp IN (111, 112, 128)
          AND t1.Date >= #{start_str}# AND t1.Date <= #{end_str}#
        GROUP BY t1.Date, m.ParentGrp
    """
    cash_data = {}
    bank_data = {}
    try:
        rs = _get_rs(sql_cash_bank)
        while not rs.EOF:
            d_val = rs.Fields("Date").Value
            grp = int(rs.Fields("ParentGrp").Value)
            amt = float(rs.Fields("Amt").Value or 0)
            if amt < 0: # Only count debits (inflows) to Cash/Bank
                ds_key = d_val.strftime("%Y-%m-%d")
                amt_in = -amt
                
                if grp == 111:
                    cash_data[ds_key] = cash_data.get(ds_key, 0) + amt_in
                elif grp in (112, 128):
                    bank_data[ds_key] = bank_data.get(ds_key, 0) + amt_in
            rs.MoveNext()
        rs.Close()
    except:
        pass

    # Combine into a timeline
    timeline = []
    current_date = start_date
    while current_date <= end_date:
        ds = current_date.strftime("%Y-%m-%d")
        ds_display = current_date.strftime("%d-%m-%Y")
        s = sales_data.get(ds, 0)
        c_s = credit_sales_data.get(ds, 0)
        r = rect_data.get(ds, 0)
        r_c = rect_count.get(ds, 0)
        p = pymt_data.get(ds, 0)
        c = cash_data.get(ds, 0)
        b = bank_data.get(ds, 0)
        
        # Only include days with some activity
        if s > 0 or r > 0 or p > 0 or c > 0 or b > 0:
            timeline.append({
                "date": ds,
                "display_date": ds_display,
                "sales": s,
                "credit_sales": c_s,
                "receipts": r,
                "receipts_count": r_c,
                "payments": p,
                "cash": c,
                "bank": b,
                "inflow": c + b
            })
            
        current_date += timedelta(days=1)
        
    return {
        "from_date": start_str,
        "to_date": end_str,
        "timeline": timeline,
        "total_sales": sum(sales_data.values()),
        "total_credit_sales": sum(credit_sales_data.values()),
        "total_receipts": sum(rect_data.values()),
        "total_receipts_count": sum(rect_count.values()),
        "total_payments": sum(pymt_data.values()),
        "total_cash": sum(cash_data.values()),
        "total_bank": sum(bank_data.values()),
        "total_inflow": sum(cash_data.values()) + sum(bank_data.values())
    }


def get_party_vch_100_cash(days=0):
    """Find sales vouchers where party is NOT Cash, but the full settlement was received in Cash.
    
    Logic:
      - Fetches all sales vouchers (VchType=9) where party != Cash ledger
      - Then for each voucher checks Tran2 RecType=1 rows for cash settlement
      - A voucher is suspicious if: cash_settled > 0 AND cash_settled ≈ vch_amt (within ₹1 tolerance)
      - Uses ₹1 tolerance (not 0.05) since Busy rounds to nearest rupee in some configurations
    """
    cash_code = 1
    try:
        cash_rs = _get_rs("SELECT Code FROM Master1 WHERE Name = '.CASH' OR Name = 'Cash' OR Name = 'CASH'")
        if not cash_rs.EOF:
            cash_code = int(cash_rs.Fields("Code").Value)
        cash_rs.Close()
    except:
        pass
    
    date_filter = ""
    if days:
        start_date = datetime.datetime.now() - datetime.timedelta(days=int(days) - 1)
        date_filter = f" AND t1.Date >= #{start_date.strftime('%Y-%m-%d')}# "
    
    sql = f"""
        SELECT t1.VchCode, t1.VchNo, t1.Date, t1.VchAmtBaseCur, m.Name as PartyName
        FROM Tran1 t1
        INNER JOIN Master1 m ON t1.MasterCode1 = m.Code
        WHERE t1.VchType = 9 AND t1.MasterCode1 <> {cash_code}
        {date_filter}
        ORDER BY t1.Date DESC, t1.VchCode DESC
    """
    
    matches = []
    try:
        rs = _get_rs(sql)
        vch_codes = []
        vch_dict = {}
        while not rs.EOF:
            vcode = int(rs.Fields("VchCode").Value)
            vchno = str(rs.Fields("VchNo").Value or "").strip()
            dt = rs.Fields("Date").Value
            date_str = dt.strftime("%d-%m-%Y") if dt else ""
            vch_amt = abs(float(rs.Fields("VchAmtBaseCur").Value or 0))
            party_name = str(rs.Fields("PartyName").Value or "")
            
            # Skip zero-amount vouchers
            if vch_amt < 0.01:
                rs.MoveNext()
                continue
            
            vch_dict[vcode] = {
                "vchno": vchno,
                "date": date_str,
                "vch_amt": vch_amt,
                "party_name": party_name,
                "cash_settled": 0.0
            }
            vch_codes.append(vcode)
            rs.MoveNext()
        rs.Close()
        
        if vch_codes:
            for i in range(0, len(vch_codes), 500):
                chunk = vch_codes[i:i+500]
                chunk_in = ",".join(map(str, chunk))
                # RecType=1 rows hold settlement/payment info; MasterCode1=cash_code means cash settlement
                sql_settle = f"""
                    SELECT VchCode, SUM(ABS(Value1)) as TotalCash 
                    FROM Tran2 
                    WHERE VchCode IN ({chunk_in}) AND RecType = 1 AND MasterCode1 = {cash_code}
                    GROUP BY VchCode
                """
                rs_s = _get_rs(sql_settle)
                while not rs_s.EOF:
                    vc = int(rs_s.Fields("VchCode").Value)
                    # Sum all cash entries for this voucher (handles split payments)
                    total_cash = abs(float(rs_s.Fields("TotalCash").Value or 0))
                    if vc in vch_dict:
                        vch_dict[vc]["cash_settled"] = total_cash
                    rs_s.MoveNext()
                rs_s.Close()
                
            for vc, vinfo in vch_dict.items():
                cs = vinfo["cash_settled"]
                va = vinfo["vch_amt"]
                # Flag if cash settlement is > 0 AND covers >= 95% of voucher amount
                # Use 95% threshold (not 100%) to handle rounding differences
                if cs > 0 and cs >= (va * 0.95):
                    matches.append({
                        "vchno": vinfo["vchno"],
                        "date": vinfo["date"],
                        "vch_amt": va,
                        "party_name": vinfo["party_name"],
                        "cash_settled": cs
                    })
        
        # Sort by date descending
        matches.sort(key=lambda x: x["date"], reverse=True)
            
    except Exception as e:
        print(f"Error getting party vch 100% cash: {e}")
        
    return matches

def get_item_sales_analysis(from_date=None, to_date=None):
    """Get item-wise sales quantity and amount aggregation."""
    from datetime import datetime, timedelta
    
    if not to_date:
        end_date = datetime.now()
    else:
        end_date = datetime.strptime(to_date, "%Y-%m-%d")
        
    if not from_date:
        start_date = end_date - timedelta(days=30)
    else:
        start_date = datetime.strptime(from_date, "%Y-%m-%d")
        
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")

    # MS Access does NOT support COUNT(DISTINCT ...).
    # So we remove InvoiceCount from main SQL and compute distinct voucher counts in Python.
    sql = f"""
        SELECT m.Name as ItemName, m.Code as ItemCode, 
               SUM(t2.D1) as TotalQty, SUM(t2.Value3) as TotalAmt
        FROM (Tran1 t1 
        INNER JOIN Tran2 t2 ON t1.VchCode = t2.VchCode)
        INNER JOIN Master1 m ON t2.MasterCode1 = m.Code
        WHERE t1.VchType = 9 AND t2.RecType = 2
          AND t1.Date >= #{start_str}# AND t1.Date <= #{end_str}#
        GROUP BY m.Name, m.Code
    """

    # Separate query to get distinct (VchCode, ItemCode) pairs for correct invoice count
    sql_pairs = f"""
        SELECT DISTINCT t2.MasterCode1 as ItemCode, t1.VchCode
        FROM Tran1 t1 
        INNER JOIN Tran2 t2 ON t1.VchCode = t2.VchCode
        WHERE t1.VchType = 9 AND t2.RecType = 2
          AND t1.Date >= #{start_str}# AND t1.Date <= #{end_str}#
    """

    data = []
    total_invoices = 0
    try:
        # Step 1: Total invoices in date range
        sql_total = f"""
            SELECT COUNT(VchCode) as TotalBills
            FROM Tran1
            WHERE VchType = 9
              AND Date >= #{start_str}# AND Date <= #{end_str}#
        """
        rs_total = _get_rs(sql_total)
        if not rs_total.EOF:
            total_invoices = int(rs_total.Fields("TotalBills").Value or 0)
        rs_total.Close()

        # Step 2: Build per-item distinct invoice count in Python
        from collections import defaultdict
        item_vcodes = defaultdict(set)
        rs_pairs = _get_rs(sql_pairs)
        while not rs_pairs.EOF:
            icode = int(rs_pairs.Fields("ItemCode").Value or 0)
            vcode = int(rs_pairs.Fields("VchCode").Value or 0)
            item_vcodes[icode].add(vcode)
            rs_pairs.MoveNext()
        rs_pairs.Close()

        # Step 3: Fetch aggregated qty/amount per item
        rs = _get_rs(sql)
        while not rs.EOF:
            item_name = str(rs.Fields("ItemName").Value or "")
            item_code = int(rs.Fields("ItemCode").Value or 0)
            qty = float(rs.Fields("TotalQty").Value or 0)
            amt = float(rs.Fields("TotalAmt").Value or 0)
            # In Busy, sales qty and amount are stored as NEGATIVE values
            abs_qty = abs(qty)
            abs_amt = abs(amt)
            # Get correct distinct invoice count from Python dict
            invoice_count = len(item_vcodes.get(item_code, set()))
            if (abs_qty > 0 or abs_amt > 0) and item_name.strip():
                data.append({
                    "item_name": item_name.strip(),
                    "item_code": item_code,
                    "qty": abs_qty,
                    "amount": abs_amt,
                    "invoice_count": invoice_count,
                    "total_invoices": total_invoices
                })
            rs.MoveNext()
        rs.Close()
    except Exception as e:
        print(f"Error getting item sales analysis: {e}")

    # Sort by invoice_count descending (most popular item first)
    data.sort(key=lambda x: x["invoice_count"], reverse=True)
    return {"items": data, "total_invoices": total_invoices}

