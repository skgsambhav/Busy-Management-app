"""
Points (KPS) queries - Loyalty points summary and detailed ledger.
"""

from datetime import datetime
from bridge.connection import _get_rs, format_out_date


def get_point_ledger_summary():
    """Get points summary - uses same DueDate filter as Busy 21 VBScript for correct balance."""
    report_date_str = datetime.now().strftime("%Y-%m-%d")
    sql = f"""
        SELECT k.MasterCode1, m.Name,
               SUM(k.Points) as TotalPoints,
               SUM(k.PointsVal) as TotalVal
        FROM KPSPoints k
        LEFT JOIN Master1 m ON k.MasterCode1 = m.Code
        WHERE k.DueDate >= #{report_date_str}# OR k.DueDate IS NULL
        GROUP BY k.MasterCode1, m.Name
    """
    rst = _get_rs(sql)

    entries = []
    raw_entries = []
    missing_codes = []

    while not rst.EOF:
        mcode = int(rst.Fields("MasterCode1").Value or 0)
        name = str(rst.Fields("Name").Value or "").strip().upper()
        pts = float(rst.Fields("TotalPoints").Value or 0.0)
        val = float(rst.Fields("TotalVal").Value or 0.0)

        if round(pts, 2) != 0 or round(val, 2) != 0:
            raw_entries.append({
                "party_code": mcode,
                "party_name": name,
                "points": round(pts, 2),
                "value": round(val, 2)
            })
            if not name and mcode > 0:
                missing_codes.append(mcode)
        rst.MoveNext()
    rst.Close()

    # Resolve missing names via BillingDet
    if missing_codes:
        code_list_str = ",".join(str(c) for c in set(missing_codes))
        sql_b = f"""
            SELECT k.MasterCode1, b.PartyName
            FROM KPSPoints k
            INNER JOIN BillingDet b ON k.VchCode = b.VchCode
            WHERE k.MasterCode1 IN ({code_list_str}) AND b.PartyName IS NOT NULL AND b.PartyName <> ''
        """
        try:
            rst_b = _get_rs(sql_b)
            name_map = {}
            while not rst_b.EOF:
                mc = int(rst_b.Fields("MasterCode1").Value or 0)
                pname = str(rst_b.Fields("PartyName").Value or "").strip().upper()
                if pname and mc not in name_map:
                    name_map[mc] = pname
                rst_b.MoveNext()
            rst_b.Close()
            for item in raw_entries:
                if not item["party_name"] and item["party_code"] in name_map:
                    item["party_name"] = name_map[item["party_code"]]
        except:
            pass

    for item in raw_entries:
        if not item["party_name"]:
            item["party_name"] = f"CONTACT #{item['party_code']}"
        entries.append(item)

    entries.sort(key=lambda x: x["party_name"])
    return entries




def get_point_ledger(party_code):
    """Get point ledger transactions with exact DB-linked Expired points and chronological balance."""
    sql = f"""
        SELECT 
            k.VchCode, k.Date, k.DueDate, k.Method, k.Points, k.PointsVal, k.C1, k.vno,
            t.VchNo as TranVchNo, t.VchType, t.VchAmtBaseCur
        FROM KPSPoints k
        LEFT JOIN Tran1 t ON k.VchCode = t.VchCode
        WHERE k.MasterCode1 = {party_code}
        ORDER BY k.Date ASC, k.VchCode ASC
    """
    rst = _get_rs(sql)
    
    voucher_map = {}
    earned_pts = {}
    earned_val = {}
    redeemed_pts = {}
    redeemed_val = {}
    
    while not rst.EOF:
        vcode = rst.Fields("VchCode").Value
        dt = rst.Fields("Date").Value
        ddt = rst.Fields("DueDate").Value
        c1 = str(rst.Fields("C1").Value or "").strip()
        pts = float(rst.Fields("Points").Value or 0.0)
        pts_val = float(rst.Fields("PointsVal").Value or 0.0)
        amt = float(rst.Fields("VchAmtBaseCur").Value or 0.0)
        vno = str(rst.Fields("TranVchNo").Value or rst.Fields("vno").Value or vcode).strip()
        vtype = int(rst.Fields("VchType").Value or 0) if rst.Fields("VchType").Value else 9
        method = float(rst.Fields("Method").Value or 0.0)
        ref_vno = rst.Fields("vno").Value
        
        is_opening = (vcode < 0) or (c1 == "Opening Points")
        if is_opening:
            rst.MoveNext()
            continue
            
        if method == 1.0:
            earned_pts[vcode] = earned_pts.get(vcode, 0.0) + pts
            earned_val[vcode] = earned_val.get(vcode, 0.0) + pts_val
        elif method == 2.0 and ref_vno:
            redeemed_pts[ref_vno] = redeemed_pts.get(ref_vno, 0.0) + abs(pts)
            redeemed_val[ref_vno] = redeemed_val.get(ref_vno, 0.0) + abs(pts_val)
        
        if vcode not in voucher_map:
            voucher_map[vcode] = {
                "vcode": vcode,
                "vno": vno,
                "vtype": vtype,
                "raw_date": dt,
                "date": format_out_date(dt, ""),
                "due_date": format_out_date(ddt, ""),
                "raw_due_date": ddt,
                "sale_amt": round(amt, 2),
                "points_in": 0.0,
                "in_value": 0.0,
                "points_out": 0.0,
                "out_value": 0.0,
                "expired_pts": 0.0,
                "expired_val": 0.0
            }
        
        v = voucher_map[vcode]
        if method == 1.0:
            v["points_in"] += pts
            v["in_value"] += pts_val
        elif method == 2.0:
            v["points_out"] += abs(pts)
            v["out_value"] += abs(pts_val)
                
        rst.MoveNext()
        
    rst.Close()
    
    vouchers = list(voucher_map.values())
    vouchers.sort(key=lambda x: (x["raw_date"] or datetime.min, x["vcode"]))
    
    report_date = datetime.now()
    
    running_bal = 0.0
    for r in vouchers:
        r["points_in"] = round(r["points_in"], 2)
        r["in_value"] = round(r["in_value"], 2)
        r["points_out"] = round(r["points_out"], 2)
        r["out_value"] = round(r["out_value"], 2)
        
        if r["raw_due_date"] and hasattr(r["raw_due_date"], "timestamp"):
            if r["raw_due_date"].timestamp() <= report_date.timestamp():
                unredeemed_pts = earned_pts.get(r["vcode"], 0.0) - redeemed_pts.get(r["vcode"], 0.0)
                unredeemed_val = earned_val.get(r["vcode"], 0.0) - redeemed_val.get(r["vcode"], 0.0)
                if unredeemed_pts > 0:
                    r["expired_pts"] = round(unredeemed_pts, 2)
                    r["expired_val"] = round(unredeemed_val, 2)
        
        running_bal += r["points_in"] - r["points_out"] - r["expired_pts"]
        r["balance"] = round(running_bal, 2)
        
        del r["raw_date"]
        del r["raw_due_date"]
        
    return vouchers

def get_point_analytics_data():
    """Get full analytics data - fast SQL approach matching Busy 21 VBScript logic."""
    report_date_str = datetime.now().strftime("%Y-%m-%d")

    # Points: same DueDate filter as VBScript (non-expired balance per customer)
    sql_pts = f"""
        SELECT k.MasterCode1, m.Name as PartyName,
               SUM(k.Points) as Balance,
               SUM(k.PointsVal) as BalanceVal
        FROM KPSPoints k
        LEFT JOIN Master1 m ON k.MasterCode1 = m.Code
        WHERE k.DueDate >= #{report_date_str}# OR k.DueDate IS NULL
        GROUP BY k.MasterCode1, m.Name
    """

    # Total earned (Method=1 only, all time)
    sql_earned = """
        SELECT k.MasterCode1,
               SUM(k.Points) as EarnedPts
        FROM KPSPoints k
        WHERE k.Method = 1
        GROUP BY k.MasterCode1
    """

    # Total redeemed (Method=2, all time, stored as negative)
    sql_redeemed = """
        SELECT k.MasterCode1,
               SUM(k.Points) as RedeemedPts
        FROM KPSPoints k
        WHERE k.Method = 2
        GROUP BY k.MasterCode1
    """

    # Sales data linked to loyalty members (with DISTINCT to avoid multi-item duplication)
    sql_sales = """
        SELECT k.MasterCode1, COUNT(k.VchCode) as InvoiceCount, SUM(t1.VchAmtBaseCur) as TotalSales
        FROM (
            SELECT DISTINCT MasterCode1, VchCode
            FROM KPSPoints
            WHERE Method = 1
        ) as k
        INNER JOIN Tran1 t1 ON k.VchCode = t1.VchCode
        WHERE t1.VchType = 9
        GROUP BY k.MasterCode1
    """

    customers = {}

    try:
        # 1. Balance (non-expired)
        rst = _get_rs(sql_pts)
        while not rst.EOF:
            mcode = int(rst.Fields("MasterCode1").Value or 0)
            name = str(rst.Fields("PartyName").Value or "").strip().upper()
            if not name: name = f"CONTACT #{mcode}"
            balance = float(rst.Fields("Balance").Value or 0.0)
            customers[mcode] = {
                "party_code": mcode,
                "party_name": name,
                "points_in": 0.0,
                "points_out": 0.0,
                "expired_pts": 0.0,
                "balance": round(balance, 2),
                "invoice_count": 0,
                "total_sales": 0.0
            }
            rst.MoveNext()
        rst.Close()

        # 2. Earned (all-time)
        rst2 = _get_rs(sql_earned)
        while not rst2.EOF:
            mcode = int(rst2.Fields("MasterCode1").Value or 0)
            pts = float(rst2.Fields("EarnedPts").Value or 0.0)
            if mcode in customers:
                customers[mcode]["points_in"] = round(pts, 2)
            rst2.MoveNext()
        rst2.Close()

        # 3. Redeemed (all-time, negative in DB)
        rst3 = _get_rs(sql_redeemed)
        while not rst3.EOF:
            mcode = int(rst3.Fields("MasterCode1").Value or 0)
            pts = float(rst3.Fields("RedeemedPts").Value or 0.0)
            if mcode in customers:
                customers[mcode]["points_out"] = round(abs(pts), 2)
            rst3.MoveNext()
        rst3.Close()

        # 4. Compute expired = earned - redeemed - balance
        for c in customers.values():
            expired = c["points_in"] - c["points_out"] - c["balance"]
            c["expired_pts"] = round(max(0.0, expired), 2)

    except Exception as e:
        print(f"Error fetching KPSPoints analytics: {e}")
        return []

    # 5. Sales data
    try:
        rs_sales = _get_rs(sql_sales)
        while not rs_sales.EOF:
            mc = int(rs_sales.Fields("MasterCode1").Value or 0)
            if mc in customers:
                customers[mc]["invoice_count"] = int(rs_sales.Fields("InvoiceCount").Value or 0)
                customers[mc]["total_sales"] = round(float(rs_sales.Fields("TotalSales").Value or 0), 2)
            rs_sales.MoveNext()
        rs_sales.Close()
    except Exception as e:
        print(f"Sales query failed: {e}")

    result = list(customers.values())
    return sorted(result, key=lambda x: x["total_sales"], reverse=True)

