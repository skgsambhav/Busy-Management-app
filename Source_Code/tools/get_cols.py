import sys
import os
import win32com.client
import pythoncom

BASE_DIR = os.path.dirname(os.path.abspath(r"C:\Users\GOPAL MARKETING\Desktop\BUSY\receipt_app\tools\voucher_approval_app.py"))
PROJECT_DIR = os.path.dirname(BASE_DIR)
sys.path.insert(0, PROJECT_DIR)

from config import DATA_PATH, COMP_CODE, DB_PASSWORD

def run():
    pythoncom.CoInitialize()
    g_conn = win32com.client.Dispatch("ADODB.Connection")
    db_path = f"{DATA_PATH}{COMP_CODE}\\db.bds"
    conn_str = f"Provider=Microsoft.Jet.OLEDB.4.0;Data Source={db_path};Jet OLEDB:Database Password={DB_PASSWORD};"
    g_conn.Open(conn_str)
    
    rs = win32com.client.Dispatch("ADODB.Recordset")
    try:
        rs.Open("SELECT Name FROM UserPreferences", g_conn)
        cols = []
        while not rs.EOF:
            cols.append(str(rs.Fields('Name').Value))
            rs.MoveNext()
        rs.Close()
    except Exception as e:
        cols = [str(e)]

    
    with open(r"C:\Users\GOPAL MARKETING\Desktop\BUSY\receipt_app\scratch_cols.txt", "w") as f:
        f.write(", ".join(cols))

if __name__ == "__main__":
    run()
