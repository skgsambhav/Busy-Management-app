# Busywin App & Busy Accounting Software Integration
**Ultimate Documentation for AI Coding Agents**

This document serves as the absolute, single source of truth for the architecture, implementation details, database schema, and standard operating procedures (SOPs) for the Busywin App integrated with Busy Win 21 Accounting Software. 

**ATTENTION FUTURE AI AGENTS:** Read this document completely before writing any code or making any assumptions about the codebase.

---

## 1. Directory Structure
```
C:\Users\GOPAL MARKETING\Desktop\BUSY\receipt_app\
├── app.py                  # 64-bit Flask Web Server (Frontend & API)
├── bfe_client.py           # 64-bit IPC Client (Manages 32-bit bridge)
├── bfe_bridge.py           # 32-bit COM & ADODB Engine (The Core Engine)
├── docs/                   # Documentation folder
│   └── PROJECT_ARCHITECTURE.md
├── static/                 # CSS (style.css) and JS (app.js, receipt_form.js)
└── templates/              # HTML Templates (base, items_list, receipt_form)
```

---

## 2. System Architecture: The 32-bit / 64-bit Bridge

The most critical constraint of this project is that **Busy's COM API (`Busy2L21.dll`) is strictly 32-bit**, whereas modern Python environments (and this Flask app) run in **64-bit**. 

To bridge this gap, the system uses an Inter-Process Communication (IPC) model:
1. **Flask Web Server (`app.py`)**: Runs in 64-bit Python. It serves the web UI and provides REST API endpoints.
2. **IPC Client (`bfe_client.py`)**: Runs in 64-bit Python alongside Flask. It uses `subprocess.Popen` to spawn a persistent 32-bit Python process (`C:\Python32\python.exe bfe_bridge.py`). It communicates with this bridge via JSON payloads over `stdin` and `stdout`.
3. **COM Bridge (`bfe_bridge.py`)**: A 32-bit Python script that initializes `win32com.client` and actually communicates with the Busy database and COM objects. **It runs infinitely in a while loop**, parsing `stdin` line by line, executing commands, and printing JSON results to `stdout`.

### Adding a New Feature (End-to-End Workflow)
If you need to add a new feature (e.g., fetching Sales Invoices), follow this exact flow:
1. **`bfe_bridge.py`**: Add a python function `get_sales_invoices()`. Add an `elif action == "get_sales_invoices":` block in the `__main__` loop to call it and return `{"data": result}`.
2. **`bfe_client.py`**: Add a wrapper function `def get_sales_invoices(): return _send_command({"cmd": "get_sales_invoices"})["data"]`.
3. **`app.py`**: Add a Flask route `@app.route("/api/sales")` that calls `bfe_client.get_sales_invoices()` and returns `jsonify()`.
4. **`static/app.js`**: Add the frontend fetch call.

---

## 3. Database Engine & Connections

`bfe_bridge.py` utilizes **two distinct connection methods** to interact with Busy. You must choose the right one depending on the task.

### A. Direct ADODB Connection (For Blazing Fast Reads/Updates)
- **Object**: `g_conn = win32com.client.Dispatch("ADODB.Connection")`
- **Use Case**: Fetching massive lists (1000+ items), modifying Item Master prices, updating names.
- **Why?**: The COM API is extremely slow for bulk data retrieval. ADODB connects directly to the `.bds` (MS Access) database files.
- **Connection String**: `Provider=Microsoft.Jet.OLEDB.4.0;Data Source=C:\BusyWin\Data\Comp0002\db12026.bds;Jet OLEDB:Database Password=ILoveMyINDIA;`
- **Password Note**: The database password for ADODB is heavily guarded by Busy. For this specific deployment, the password is **`ILoveMyINDIA`**. 

### B. BFE COM Object (For Complex Transactions)
- **Object**: `g_dm = win32com.client.Dispatch("Busy2L21.CDataManager")` (and related services).
- **Use Case**: Creating vouchers (Receipts, Sales, Payments).
- **Why?**: Creating an accounting voucher requires updating 10+ tables (Tran1, Tran2, Tran3, Folio1, etc.) with complex double-entry rules. The BFE COM object handles all of this natively via XML payloads (e.g., `CTranServices.AddTrans`). **NEVER insert transactions manually via ADODB.**

---

## 4. Database Schema Deep Dive

### `Master1` Table (The Core Master Table)
This table holds all Ledgers, Groups, and Items.
- **Primary Key**: `Code` (Integer)
- **MasterType Discriminator**:
  - `1` = Account Groups (e.g., Sundry Debtors)
  - `2` = Ledgers (Parties, Bank Accounts, Cash)
  - `6` = Items (Inventory)
- **Item Pricing Mapping** (`MasterType = 6`):
  - `D2` = M.R.P. (Note: Busy dynamically maps D columns in `db.bds`. For this company, MRP is mapped to `D2`).
  - `D3` = Sale Price
  - `D4` = Purchase Price
  - `Name` = Item Name (English)
  - `NameSL` = Second Language Name (Hindi alias / Unicode)
  - `PrintName` = Print Name (English)
  - `PrintNameSL` = Print Name (Hindi / Unicode)

### `MasterSupport` Table (Additional Price Lists)
Busy stores Sale Price Level (A), (B), and (C) as key-value pairs.
- `MasterCode` = Item Code (FK to Master1)
- `I2` = 9 (Fixed identifier for Sales Price list)
- `I1` = 101 (Price A), 102 (Price B), 103 (Price C)
- `D1` = The price value.

### `Tran1`, `Tran2`, `Tran3` (Transactions)
- **Tran1**: Voucher headers. (`VchType 14` = Receipt).
- **Tran2**: Voucher line items (`RecType 1` = Ledger entry). **Sign Convention**: Negative `Value1` = Debit (Dr), Positive = Credit (Cr).
- **Tran3**: Bill-wise references (outstanding tracking against specific invoices).

---

## 5. UI/UX Paradigm
- The frontend uses pure HTML, Vanilla JS, and Vanilla CSS. **Do not introduce heavy frameworks (React/Vue/Tailwind) unless requested.**
- **Design System**: "Glassmorphism" dark theme. Heavy use of CSS variables (`var(--bg-card)`, `var(--accent-cyan)`), backdrop filters, and subtle border opacities (`rgba(255,255,255,0.1)`).
- **Modals**: Must use `max-height: 90vh; overflow-y: auto;` to prevent form action buttons from being cut off on smaller screens.
- **Toast Notifications**: Used for non-intrusive success/error messages.

---

## 6. Critical Debugging Rules for AI Agents

1. **Flask Caching & Restarting**: 
   - `bfe_client.py` spawns `bfe_bridge.py` ONCE and keeps it alive. 
   - **If you modify `bfe_bridge.py`, your changes WILL NOT take effect until you kill the Flask server and restart it!** Use `manage_task` tool to kill the Flask task and `run_command` to restart it.
2. **Bash Commands Constraint**: 
   - You are running in a Windows environment (Powershell). 
   - Do NOT use Linux idioms like `cat` inside bash. Rely entirely on your native tools (`read_file`, `view_file`, `multi_replace_file_content`, `grep_search`).
3. **Database Locks**: 
   - Busy locks the MS Access database files aggressively. If `bfe_bridge.py` crashes, it might leave an orphaned 32-bit python process holding a lock. If you get "Database is locked" errors, kill all Python processes (`taskkill /F /IM python.exe`).
4. **String Escaping in SQL**: 
   - When updating names in `Master1` via ADODB, **always escape single quotes** (e.g., `safe_name = name.replace("'", "''")`).
5. **Unicode in Python**: 
   - Hindi names (`NameSL`, `PrintNameSL`) contain Devanagari Unicode. If you write Python scripts to print these to stdout, they will throw `UnicodeEncodeError` in cp1252 consoles. Write them to `utf-8` encoded files instead of printing.
