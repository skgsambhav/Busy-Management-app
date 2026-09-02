import win32com.client
import pythoncom
import time
import os
import sys
import io
from deep_translator import GoogleTranslator

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

def update_hindi_names():
    pythoncom.CoInitialize()
    
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from config import DATA_PATH, COMP_CODE, DB_PASSWORD
    
    comp_dir = os.path.join(DATA_PATH, COMP_CODE)
    db_path = None
    if os.path.exists(comp_dir):
        bds_files = [f for f in os.listdir(comp_dir) if f.startswith('db1') and f.endswith('.bds')]
        if bds_files:
            bds_files.sort(reverse=True)
            db_path = os.path.join(comp_dir, bds_files[0])
            
    if not db_path:
        print(f"Database file not found in {comp_dir}")
        return

    pwd = DB_PASSWORD
    conn_str = f"Provider=Microsoft.Jet.OLEDB.4.0;Data Source={db_path};Jet OLEDB:Database Password={pwd};"
    
    conn = win32com.client.Dispatch('ADODB.Connection')
    conn.Open(conn_str)
    
    # Get all Accounts (MasterType 2 & 1) and Items (MasterType 6) where NameSL is NULL or empty
    sql_select = "SELECT Code, Name, NameSL, MasterType FROM Master1 WHERE (MasterType = 6 OR MasterType = 2 OR MasterType = 1) AND (NameSL IS NULL OR NameSL = '')"
    rs = win32com.client.Dispatch('ADODB.Recordset')
    rs.Open(sql_select, conn)
    
    masters_to_translate = []
    while not rs.EOF:
        code = rs.Fields('Code').Value
        name = rs.Fields('Name').Value
        mtype = rs.Fields('MasterType').Value
        if name and str(name).strip():
            masters_to_translate.append((code, str(name).strip(), mtype))
        rs.MoveNext()
    rs.Close()
    
    print(f"Found {len(masters_to_translate)} accounts and items missing Hindi names.")
    if not masters_to_translate:
        conn.Close()
        print("Done! Successfully updated 0 accounts/items with Hindi names.")
        return
        
    translator = GoogleTranslator(source='en', target='hi')
    
    updated_count = 0
    for code, name, mtype in masters_to_translate:
        try:
            hindi_name = translator.translate(name)
            if hindi_name:
                safe_name = hindi_name.replace("'", "''")
                sql_update = f"UPDATE Master1 SET NameSL = '{safe_name}' WHERE Code = {code}"
                conn.Execute(sql_update)
                m_label = "Item" if mtype == 6 else "Account"
                print(f"Translated [{m_label}]: {name} -> {hindi_name}")
                updated_count += 1
                time.sleep(0.3)
        except Exception as e:
            print(f"Failed to translate {name}: {e}")
            time.sleep(0.5)
            
    conn.Close()
    print(f"Done! Successfully updated {updated_count} accounts/items with Hindi names.")

if __name__ == "__main__":
    update_hindi_names()
