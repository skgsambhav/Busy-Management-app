"""
Item queries - Stock items listing and price updates via BFE COM.

UPDATE METHOD: 
1. Updates all data (prices, names, descriptions) directly via ADODB SQL. This ensures
   100% compatibility with all fields (Price A/B/C, Date-Wise prices, Hindi names, etc)
   without complex XML parsing.
2. Triggers a BFE "Dummy Save" (Load1 -> Save) on the item. This forces Busy's engine
   to re-read the database and regenerate the MastFootPrint, Folio1, DailySum checksums.
   No more "Update Master Balances" errors!
"""

import re
import time
import win32com.client
from config import BFE_PREFIX
from bridge.connection import _get_rs, g_conn_ref


def get_items():
    """Get all Stock Items with pricing and unit."""
    sql = """
        SELECT m.Code, m.Name, m.NameSL, m.D3 AS SalePrice, m.D4 AS PurcPrice, m.D2 AS MRP, u.Name AS UnitName,
               (SELECT Name FROM Master1 WHERE Code = m.ParentGrp) AS GrpName,
               (SELECT TOP 1 D1 FROM MasterSupport WHERE MasterCode = m.Code AND I2 = 9 AND I1 = 101) AS PriceA,
               (SELECT TOP 1 D1 FROM MasterSupport WHERE MasterCode = m.Code AND I2 = 9 AND I1 = 102) AS PriceB,
               (SELECT TOP 1 D1 FROM MasterSupport WHERE MasterCode = m.Code AND I2 = 9 AND I1 = 103) AS PriceC,
               (SELECT TOP 1 Address1 FROM MasterAddressInfo WHERE MasterCode = m.Code) AS Desc1,
               (SELECT TOP 1 Address2 FROM MasterAddressInfo WHERE MasterCode = m.Code) AS Desc2,
               (SELECT TOP 1 Address3 FROM MasterAddressInfo WHERE MasterCode = m.Code) AS Desc3,
               (SELECT TOP 1 Address4 FROM MasterAddressInfo WHERE MasterCode = m.Code) AS Desc4
        FROM Master1 m
        LEFT JOIN Master1 u ON m.CM1 = u.Code
        WHERE m.MasterType = 6
          AND (m.DeactiveMaster = 0 OR m.DeactiveMaster IS NULL)
        ORDER BY m.Name
    """
    g_conn = g_conn_ref()
    rst = _get_rs(sql)
    items = []
    while not rst.EOF:
        code = int(rst.Fields("Code").Value)
        name = str(rst.Fields("Name").Value or "").strip()
        mrp = float(rst.Fields("MRP").Value or 0)
        
        # Auto-detect MRP from item name if MRP is 0
        if mrp == 0:
            match = re.search(r'(\d+(?:\.\d+)?)\s*\/-\s*', name)
            if match:
                try:
                    extracted_mrp = float(match.group(1))
                    if extracted_mrp > 0:
                        mrp = extracted_mrp
                        g_conn.Execute(f"UPDATE Master1 SET D2 = {extracted_mrp} WHERE Code = {code} AND MasterType = 6")
                except Exception:
                    pass

        items.append({
            "code": code,
            "name": name,
            "name_sl": str(rst.Fields("NameSL").Value or "").strip(),
            "group": str(rst.Fields("GrpName").Value or "").strip(),
            "unit": str(rst.Fields("UnitName").Value or "").strip(),
            "sale_price": float(rst.Fields("SalePrice").Value or 0),
            "purc_price": float(rst.Fields("PurcPrice").Value or 0),
            "mrp": mrp,
            "price_a": float(rst.Fields("PriceA").Value or 0),
            "price_b": float(rst.Fields("PriceB").Value or 0),
            "price_c": float(rst.Fields("PriceC").Value or 0),
            "desc1": str(rst.Fields("Desc1").Value or "").strip(),
            "desc2": str(rst.Fields("Desc2").Value or "").strip(),
            "desc3": str(rst.Fields("Desc3").Value or "").strip(),
            "desc4": str(rst.Fields("Desc4").Value or "").strip()
        })
        rst.MoveNext()
    rst.Close()
    return items


def update_item_prices(item_code, sale_price, purc_price, mrp, price_a=0, price_b=0, price_c=0, name_sl=None, desc1=None, desc2=None, desc3=None, desc4=None):
    """
    Update item prices safely avoiding the 'Update Master Balances' error.
    
    Flow: 
    1. Update all fields directly via ADODB (safest for ALL fields, date-wise prices, etc).
    2. Force BFE to reload and save the item to recalculate MastFootPrint checksums.
    """
    g_conn = g_conn_ref()
    item_code = int(item_code)
    
    def _safe_execute(sql, retries=5):
        """Execute SQL with retry for lock conflicts."""
        for attempt in range(retries):
            try:
                g_conn.Execute(sql)
                return
            except Exception as e:
                err_str = str(e)
                if attempt < retries - 1 and ("same data" in err_str or "locked" in err_str or "2147352567" in err_str):
                    time.sleep(0.5 + attempt * 0.3)
                else:
                    raise

    try:
        # =========================================================================
        # 1. DIRECT ADODB UPDATES (100% Reliable for all fields)
        # =========================================================================
        
        # Update Main Prices (SalePrice=D3, PurcPrice=D4, MRP=D2)
        _safe_execute(f"UPDATE Master1 SET D3 = {float(sale_price)}, D4 = {float(purc_price)}, D2 = {float(mrp)} WHERE Code = {item_code} AND MasterType = 6")
        
        # Update Hindi name if provided
        if name_sl is not None:
            safe_sl = name_sl.replace("'", "''")
            _safe_execute(f"UPDATE Master1 SET NameSL = '{safe_sl}', PrintNameSL = '{safe_sl}' WHERE Code = {item_code} AND MasterType = 6")
        
        # Update Price A/B/C via MasterSupport
        def upsert_support(cat_i1, val):
            val = float(val)
            rs = _get_rs(f"SELECT MasterCode FROM MasterSupport WHERE MasterCode={item_code} AND I2=9 AND I1={cat_i1}")
            exists = not rs.EOF
            rs.Close()
            if exists:
                _safe_execute(f"UPDATE MasterSupport SET D1 = {val} WHERE MasterCode={item_code} AND I2=9 AND I1={cat_i1}")
            else:
                _safe_execute(f"INSERT INTO MasterSupport (MasterCode, MasterType, I1, I2, D1, [Date]) VALUES ({item_code}, 6, {cat_i1}, 9, {val}, #2026-04-01#)")
                
        if price_a or price_b or price_c:
            upsert_support(101, price_a)
            upsert_support(102, price_b)
            upsert_support(103, price_c)
            
            # Also update the Date-Wise pricing block if it exists (I1=144, 145, 146 for Price DateWise 1, 2, 3)
            # This ensures MultiPricesDateWise XML block is also kept in sync if active
            upsert_support(144, price_a)
            upsert_support(145, price_b)
            upsert_support(146, price_c)
            
        # Update item descriptions if provided
        if desc1 is not None or desc2 is not None or desc3 is not None or desc4 is not None:
            rs_addr = _get_rs(f"SELECT MasterCode FROM MasterAddressInfo WHERE MasterCode={item_code}")
            addr_exists = not rs_addr.EOF
            rs_addr.Close()
            safe_d1 = (desc1 or "").replace("'", "''")
            safe_d2 = (desc2 or "").replace("'", "''")
            safe_d3 = (desc3 or "").replace("'", "''")
            safe_d4 = (desc4 or "").replace("'", "''")
            if addr_exists:
                _safe_execute(f"UPDATE MasterAddressInfo SET Address1 = '{safe_d1}', Address2 = '{safe_d2}', Address3 = '{safe_d3}', Address4 = '{safe_d4}' WHERE MasterCode={item_code}")
            else:
                _safe_execute(f"INSERT INTO MasterAddressInfo (MasterCode, Address1, Address2, Address3, Address4) VALUES ({item_code}, '{safe_d1}', '{safe_d2}', '{safe_d3}', '{safe_d4}')")

        # =========================================================================
        # 2. TRIGGER BFE FOOTPRINT REBUILD (Prevents "Update Master" error)
        # =========================================================================
        # Tell BFE to load the newly updated DB data and save it back.
        # This regenerates the MastFootPrint checksums perfectly.
        
        try:
            # Brief pause to let Jet DB Engine flush the ADODB writes before BFE reads them
            time.sleep(0.5)
            
            im = win32com.client.Dispatch(f"{BFE_PREFIX}.CItemMast")
            
            load_result = None
            for attempt in range(3):
                try:
                    load_result = im.Load1(item_code)
                    break
                except Exception as e:
                    if attempt < 2 and "Subscript out of range" in str(e):
                        time.sleep(1)
                    else:
                        raise
                        
            loaded_ok = load_result[0] if isinstance(load_result, tuple) else load_result
            if loaded_ok:
                im.ModifyMaster = True
                im.ForceCode(item_code)
                
                err_msg = ""
                save_result = im.Save(err_msg)
                save_ok = save_result[0] if isinstance(save_result, tuple) else save_result
                save_err = save_result[1] if isinstance(save_result, tuple) and len(save_result) > 1 else ""
                
                if not save_ok:
                    print(f"Warning: BFE footprint rebuild failed for {item_code}: {save_err}")
        except Exception as e:
            # We don't want to crash the API if BFE dummy save fails, because the ADODB
            # update (which actually changes the prices) has already succeeded.
            print(f"Warning: BFE footprint rebuild exception for {item_code}: {e}")
                
        return {"success": True, "method": "Hybrid BFE"}
        
    except Exception as e:
        raise Exception(f"Failed to update item prices: {e}")
