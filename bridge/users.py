from bridge.connection import _get_rs
import datetime

def get_user_performance_metrics(from_date=None, to_date=None):
    """Get aggregated daily sales and receipts grouped by user between dates."""
    
    if not to_date:
        end_date = datetime.datetime.now()
    else:
        end_date = datetime.datetime.strptime(to_date, "%Y-%m-%d")
        
    if not from_date:
        start_date = end_date - datetime.timedelta(days=30)
    else:
        start_date = datetime.datetime.strptime(from_date, "%Y-%m-%d")
        
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")
    
    # 1. Get Aggregated User Totals
    sql_totals = f"""
        SELECT c.UserName, t1.VchType, COUNT(t1.VchCode) as VchCount, SUM(t1.VchAmtBaseCur) as TotalAmount
        FROM CheckList c
        INNER JOIN Tran1 t1 ON c.Code = t1.VchCode
        WHERE c.Type = 2 AND c.Action = 1 AND t1.VchType IN (9, 14)
          AND t1.Date >= #{start_str}# AND t1.Date <= #{end_str}#
        GROUP BY c.UserName, t1.VchType
    """
    
    user_totals = {}
    try:
        rs = _get_rs(sql_totals)
        while not rs.EOF:
            user = str(rs.Fields('UserName').Value or "").strip()
            vch_type = int(rs.Fields('VchType').Value)
            count = int(rs.Fields('VchCount').Value or 0)
            amount = float(rs.Fields('TotalAmount').Value or 0)
            
            if user not in user_totals:
                user_totals[user] = {"sales_count": 0, "sales_amount": 0, "receipts_count": 0, "receipts_amount": 0, "sales_items": 0}
                
            if vch_type == 9:
                user_totals[user]["sales_count"] += count
                user_totals[user]["sales_amount"] += amount
            elif vch_type == 14:
                user_totals[user]["receipts_count"] += count
                user_totals[user]["receipts_amount"] += amount
                
            rs.MoveNext()
        rs.Close()
    except Exception as e:
        print(f"Error getting user performance totals: {e}")

    # 1.1 Get Aggregated User Sales Items (Distinct count of items/lines)
    sql_qty = f"""
        SELECT c.UserName, COUNT(t2.SrNo) as TotalItems
        FROM (CheckList c
        INNER JOIN Tran1 t1 ON c.Code = t1.VchCode)
        INNER JOIN Tran2 t2 ON t1.VchCode = t2.VchCode
        WHERE c.Type = 2 AND c.Action = 1 AND t1.VchType = 9 AND t2.RecType = 2
          AND t1.Date >= #{start_str}# AND t1.Date <= #{end_str}#
        GROUP BY c.UserName
    """
    try:
        rs = _get_rs(sql_qty)
        while not rs.EOF:
            user = str(rs.Fields('UserName').Value or "").strip()
            qty = int(rs.Fields('TotalItems').Value or 0)
            if user in user_totals:
                user_totals[user]["sales_items"] = qty
            rs.MoveNext()
        rs.Close()
    except Exception as e:
        print(f"Error getting user sales quantities: {e}")

    # 2. Get Daily Timeline per user
    sql_timeline = f"""
        SELECT c.UserName, t1.Date, t1.VchType, COUNT(t1.VchCode) as VchCount, SUM(t1.VchAmtBaseCur) as TotalAmount
        FROM CheckList c
        INNER JOIN Tran1 t1 ON c.Code = t1.VchCode
        WHERE c.Type = 2 AND c.Action = 1 AND t1.VchType IN (9, 14)
          AND t1.Date >= #{start_str}# AND t1.Date <= #{end_str}#
        GROUP BY c.UserName, t1.Date, t1.VchType
    """
    
    daily_data = {}
    try:
        rs = _get_rs(sql_timeline)
        while not rs.EOF:
            user = str(rs.Fields('UserName').Value or "").strip()
            d_val = rs.Fields('Date').Value
            vch_type = int(rs.Fields('VchType').Value)
            count = int(rs.Fields('VchCount').Value or 0)
            amount = float(rs.Fields('TotalAmount').Value or 0)
            
            if d_val:
                ds_key = d_val.strftime("%Y-%m-%d")
                if ds_key not in daily_data:
                    daily_data[ds_key] = {}
                if user not in daily_data[ds_key]:
                    daily_data[ds_key][user] = {"sales_count": 0, "sales_amount": 0, "receipts_count": 0, "receipts_amount": 0}
                    
                if vch_type == 9:
                    daily_data[ds_key][user]["sales_count"] += count
                    daily_data[ds_key][user]["sales_amount"] += amount
                elif vch_type == 14:
                    daily_data[ds_key][user]["receipts_count"] += count
                    daily_data[ds_key][user]["receipts_amount"] += amount
            rs.MoveNext()
        rs.Close()
    except Exception as e:
        print(f"Error getting user performance timeline: {e}")

    # Combine into a timeline array (filling missing dates)
    timeline = []
    current_date = start_date
    while current_date <= end_date:
        ds = current_date.strftime("%Y-%m-%d")
        ds_display = current_date.strftime("%d-%m-%Y")
        
        # Skip Tuesday completely from the graph timeline
        if current_date.weekday() == 1:
            current_date += datetime.timedelta(days=1)
            continue
            
        day_users = daily_data.get(ds, {})
        timeline.append({
            "date": ds,
            "display_date": ds_display,
            "users": day_users
        })
        current_date += datetime.timedelta(days=1)
        
    return {
        "from_date": start_str,
        "to_date": end_str,
        "users": user_totals,
        "timeline": timeline
    }

def get_user_vouchers(username, from_date=None, to_date=None):
    """Get the list of sales and receipts created by a user between dates."""
    if not to_date:
        end_date = datetime.datetime.now()
    else:
        end_date = datetime.datetime.strptime(to_date, "%Y-%m-%d")
        
    if not from_date:
        start_date = end_date - datetime.timedelta(days=30)
    else:
        start_date = datetime.datetime.strptime(from_date, "%Y-%m-%d")
        
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")
    
    sql = f"""
        SELECT t1.VchCode, t1.VchNo, t1.Date, t1.VchType, t1.VchAmtBaseCur
        FROM CheckList c
        INNER JOIN Tran1 t1 ON c.Code = t1.VchCode
        WHERE c.Type = 2 AND c.Action = 1 
          AND c.UserName = '{username}'
          AND t1.VchType IN (9, 14)
          AND t1.Date >= #{start_str}# AND t1.Date <= #{end_str}#
        ORDER BY t1.Date DESC, t1.VchCode DESC
    """
    
    vouchers = []
    try:
        rs = _get_rs(sql)
        while not rs.EOF:
            vcode = int(rs.Fields('VchCode').Value)
            v_type = int(rs.Fields('VchType').Value)
            type_str = "Sale" if v_type == 9 else "Receipt" if v_type == 14 else str(v_type)
            
            d_val = rs.Fields('Date').Value
            date_str = d_val.strftime("%d-%m-%Y") if d_val else ""
            
            vouchers.append({
                "vcode": vcode,
                "vchno": str(rs.Fields('VchNo').Value or "").strip(),
                "date": date_str,
                "type": type_str,
                "amount": float(rs.Fields('VchAmtBaseCur').Value or 0)
            })
            rs.MoveNext()
        rs.Close()
    except Exception as e:
        print(f"Error getting user vouchers for {username}: {e}")
        
    return vouchers

def get_employee_performance_metrics(from_date=None, to_date=None):
    """Get aggregated daily sales billed and packed grouped by employee between dates."""
    if not to_date:
        end_date = datetime.datetime.now()
    else:
        end_date = datetime.datetime.strptime(to_date, "%Y-%m-%d")
        
    if not from_date:
        start_date = end_date - datetime.timedelta(days=30)
    else:
        start_date = datetime.datetime.strptime(from_date, "%Y-%m-%d")
        
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")
    
    emp_totals = {}
    
    def get_or_create_emp(emp_name):
        if emp_name not in emp_totals:
            emp_totals[emp_name] = {"sales_count": 0, "sales_amount": 0, "billed_count": 0, "billed_amount": 0, "packed_count": 0}
        return emp_totals[emp_name]

    # 1. Salesman Totals (OF7)
    sql_sales = f"""
        SELECT vo.OF7 as Employee, COUNT(t1.VchCode) as VchCount, SUM(t1.VchAmtBaseCur) as VchAmount
        FROM Tran1 t1
        INNER JOIN VchOtherInfo vo ON t1.VchCode = vo.VchCode
        WHERE t1.VchType = 9 AND t1.Date >= #{start_str}# AND t1.Date <= #{end_str}#
          AND vo.OF7 IS NOT NULL 
        GROUP BY vo.OF7
    """
    try:
        rs = _get_rs(sql_sales)
        while not rs.EOF:
            emp = str(rs.Fields('Employee').Value or "").strip()
            if emp and emp.upper() != "N/A":
                d = get_or_create_emp(emp)
                d["sales_count"] += int(rs.Fields('VchCount').Value or 0)
                d["sales_amount"] += float(rs.Fields('VchAmount').Value or 0)
            rs.MoveNext()
        rs.Close()
    except Exception as e:
        print(f"Error getting salesman totals: {e}")

    # 2. Billed By Totals (OF8)
    sql_billed = f"""
        SELECT vo.OF8 as Employee, COUNT(t1.VchCode) as BilledCount, SUM(t1.VchAmtBaseCur) as BilledAmount
        FROM Tran1 t1
        INNER JOIN VchOtherInfo vo ON t1.VchCode = vo.VchCode
        WHERE t1.VchType = 9 AND t1.Date >= #{start_str}# AND t1.Date <= #{end_str}#
          AND vo.OF8 IS NOT NULL 
        GROUP BY vo.OF8
    """
    try:
        rs = _get_rs(sql_billed)
        while not rs.EOF:
            emp = str(rs.Fields('Employee').Value or "").strip()
            if emp and emp.upper() != "N/A":
                d = get_or_create_emp(emp)
                d["billed_count"] += int(rs.Fields('BilledCount').Value or 0)
                d["billed_amount"] += float(rs.Fields('BilledAmount').Value or 0)
            rs.MoveNext()
        rs.Close()
    except Exception as e:
        pass

    # 3. Packed By Totals (OF9)
    sql_packed = f"""
        SELECT vo.OF9 as Employee, COUNT(t1.VchCode) as PackedCount
        FROM Tran1 t1
        INNER JOIN VchOtherInfo vo ON t1.VchCode = vo.VchCode
        WHERE t1.VchType = 9 AND t1.Date >= #{start_str}# AND t1.Date <= #{end_str}#
          AND vo.OF9 IS NOT NULL 
        GROUP BY vo.OF9
    """
    try:
        rs = _get_rs(sql_packed)
        while not rs.EOF:
            emp = str(rs.Fields('Employee').Value or "").strip()
            if emp and emp.upper() != "N/A":
                d = get_or_create_emp(emp)
                d["packed_count"] += int(rs.Fields('PackedCount').Value or 0)
            rs.MoveNext()
        rs.Close()
    except Exception as e:
        pass

    # Timeline Logic
    daily_data = {}
    
    def get_or_create_daily(d_val, emp_name):
        ds_key = d_val.strftime("%Y-%m-%d")
        if ds_key not in daily_data:
            daily_data[ds_key] = {}
        if emp_name not in daily_data[ds_key]:
            daily_data[ds_key][emp_name] = {"sales_count": 0, "billed_count": 0, "packed_count": 0}
        return daily_data[ds_key][emp_name]

    # Timeline Salesman
    try:
        sql = f"SELECT t1.Date, vo.OF7 as Employee, COUNT(t1.VchCode) as Cnt FROM Tran1 t1 INNER JOIN VchOtherInfo vo ON t1.VchCode = vo.VchCode WHERE t1.VchType = 9 AND t1.Date >= #{start_str}# AND t1.Date <= #{end_str}# AND vo.OF7 IS NOT NULL GROUP BY t1.Date, vo.OF7"
        rs = _get_rs(sql)
        while not rs.EOF:
            d_val = rs.Fields('Date').Value
            emp = str(rs.Fields('Employee').Value or "").strip()
            if d_val and emp and emp.upper() != "N/A":
                d = get_or_create_daily(d_val, emp)
                d["sales_count"] += int(rs.Fields('Cnt').Value or 0)
            rs.MoveNext()
        rs.Close()
    except: pass
    
    # Timeline Billed By
    try:
        sql = f"SELECT t1.Date, vo.OF8 as Employee, COUNT(t1.VchCode) as Cnt FROM Tran1 t1 INNER JOIN VchOtherInfo vo ON t1.VchCode = vo.VchCode WHERE t1.VchType = 9 AND t1.Date >= #{start_str}# AND t1.Date <= #{end_str}# AND vo.OF8 IS NOT NULL GROUP BY t1.Date, vo.OF8"
        rs = _get_rs(sql)
        while not rs.EOF:
            d_val = rs.Fields('Date').Value
            emp = str(rs.Fields('Employee').Value or "").strip()
            if d_val and emp and emp.upper() != "N/A":
                d = get_or_create_daily(d_val, emp)
                d["billed_count"] += int(rs.Fields('Cnt').Value or 0)
            rs.MoveNext()
        rs.Close()
    except: pass

    # Timeline Packed By
    try:
        sql = f"SELECT t1.Date, vo.OF9 as Employee, COUNT(t1.VchCode) as Cnt FROM Tran1 t1 INNER JOIN VchOtherInfo vo ON t1.VchCode = vo.VchCode WHERE t1.VchType = 9 AND t1.Date >= #{start_str}# AND t1.Date <= #{end_str}# AND vo.OF9 IS NOT NULL GROUP BY t1.Date, vo.OF9"
        rs = _get_rs(sql)
        while not rs.EOF:
            d_val = rs.Fields('Date').Value
            emp = str(rs.Fields('Employee').Value or "").strip()
            if d_val and emp and emp.upper() != "N/A":
                d = get_or_create_daily(d_val, emp)
                d["packed_count"] += int(rs.Fields('Cnt').Value or 0)
            rs.MoveNext()
        rs.Close()
    except: pass

    timeline = []
    current_date = start_date
    while current_date <= end_date:
        ds = current_date.strftime("%Y-%m-%d")
        ds_display = current_date.strftime("%d-%m-%Y")
        if current_date.weekday() == 1:
            current_date += datetime.timedelta(days=1)
            continue
        day_emps = daily_data.get(ds, {})
        timeline.append({"date": ds, "display_date": ds_display, "employees": day_emps})
        current_date += datetime.timedelta(days=1)
        
    return {
        "from_date": start_str,
        "to_date": end_str,
        "employees": emp_totals,
        "timeline": timeline
    }
