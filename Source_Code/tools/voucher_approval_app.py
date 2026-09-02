import sys
import os
import time
import sqlite3
import datetime
import tkinter as tk
from tkinter import ttk, messagebox
import threading
import winsound
import logging
import customtkinter as ctk

# Ensure we can find the project root and import bridge/config
if getattr(sys, 'frozen', False):
    # If bundled via PyInstaller, use the fixed absolute path for the DB and config
    PROJECT_DIR = r"C:\Users\GOPAL MARKETING\Desktop\BUSY\receipt_app"
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    PROJECT_DIR = os.path.dirname(BASE_DIR)

sys.path.insert(0, PROJECT_DIR)

DB_PATH = os.path.join(PROJECT_DIR, "data", "approvals.db")
LOG_PATH = os.path.join(PROJECT_DIR, "data", "voucher_app.log")
logging.basicConfig(filename=LOG_PATH, level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logging.info("Starting Voucher Approval Utility (CTK)...")

INTERVAL_MS = 30000  # 30 seconds auto-refresh

def init_db():
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('PRAGMA journal_mode=WAL;')
        c.execute('''
            CREATE TABLE IF NOT EXISTS approvals (
                vchcode INTEGER PRIMARY KEY,
                vchno TEXT,
                amount REAL,
                status TEXT,
                approved_at TIMESTAMP
            )
        ''')
        try:
            c.execute("ALTER TABLE approvals ADD COLUMN approval_count INTEGER DEFAULT 0")
            c.execute("ALTER TABLE approvals ADD COLUMN previous_amount REAL DEFAULT 0")
        except sqlite3.OperationalError:
            pass
        conn.commit()
        conn.close()
    except sqlite3.Error as e:
        logging.error(f"Database Initialization Error: {e}")

# Set appearance mode and color theme
ctk.set_appearance_mode("System")  # Modes: "System" (standard), "Dark", "Light"
ctk.set_default_color_theme("blue")  # Themes: "blue" (standard), "green", "dark-blue"

class VoucherApprovalApp:
    def __init__(self, root):
        self.root = root
        self.root.title("🌟 Busy Voucher Approval")
        self.root.geometry("550x750")
        self.root.attributes('-topmost', True)
        
        self.bfe_active = False
        self.get_rs_func = None
        self.is_locked = True
        
        self.last_beep_time = 0
        self.prev_unapproved_count = 0
        
        self.setup_ui()
        init_db()
        
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Start BFE connection in background
        threading.Thread(target=self.init_bfe, daemon=True).start()

    def on_closing(self):
        logging.info("Application shutting down by user...")
        self.root.destroy()
        os._exit(0)

    def setup_ui(self):
        # Top Frame for Controls
        top_frame = ctk.CTkFrame(self.root, corner_radius=10, fg_color="transparent")
        top_frame.pack(fill=ctk.X, pady=(15, 5), padx=20)
        
        self.lbl_status = ctk.CTkLabel(top_frame, text="⏳ BFE...", font=ctk.CTkFont(size=14, weight="bold"), text_color="#f1c40f")
        self.lbl_status.pack(side=ctk.LEFT)
        
        self.btn_lock = ctk.CTkButton(top_frame, text="🔒", width=45, height=35, command=self.toggle_lock, fg_color="#e74c3c", hover_color="#c0392b", font=ctk.CTkFont(size=18))
        self.btn_lock.pack(side=ctk.RIGHT, padx=5)
        
        self.btn_refresh = ctk.CTkButton(top_frame, text="🔄", width=45, height=35, command=self.refresh_data, state="disabled", fg_color="#e67e22", hover_color="#d35400", font=ctk.CTkFont(size=18))
        self.btn_refresh.pack(side=ctk.RIGHT, padx=5)
        
        # Tabs
        self.tabview = ctk.CTkTabview(self.root)
        self.tabview.pack(fill=ctk.BOTH, expand=True, padx=20, pady=(10, 10))
        
        self.tab_unapp = self.tabview.add(" ❌ Pending ")
        self.tab_app = self.tabview.add(" ✅ Approved ")
        self.tabview.set(" ❌ Pending ")

        # --- UNAPPROVED TAB ---
        # Scrollable Frame for Cards
        self.cards_frame = ctk.CTkScrollableFrame(self.tab_unapp, fg_color="transparent")
        self.cards_frame.pack(fill=ctk.BOTH, expand=True, pady=(0, 10))
        
        act_frame_unapp = ctk.CTkFrame(self.tab_unapp, fg_color="transparent")
        act_frame_unapp.pack(fill=ctk.X)
        self.btn_approve = ctk.CTkButton(act_frame_unapp, text="✅ Approve All", command=self.approve_all, state="disabled", fg_color="#27ae60", hover_color="#2ecc71", font=ctk.CTkFont(size=14, weight="bold"), height=35)
        self.btn_approve.pack(side=ctk.RIGHT, pady=5)
        
        # --- APPROVED TAB ---
        # Styling Treeview to match CTk Theme roughly
        style = ttk.Style()
        style.theme_use("clam")
        
        bg_color = self.root._apply_appearance_mode(ctk.ThemeManager.theme["CTkFrame"]["fg_color"])
        text_color = self.root._apply_appearance_mode(ctk.ThemeManager.theme["CTkLabel"]["text_color"])
        selected_color = self.root._apply_appearance_mode(ctk.ThemeManager.theme["CTkButton"]["fg_color"])
        
        style.configure("Treeview", 
                        background=bg_color,
                        foreground=text_color,
                        rowheight=35,
                        fieldbackground=bg_color,
                        borderwidth=0,
                        font=("Segoe UI", 10))
        style.configure("Treeview.Heading", 
                        background="#1f538d", 
                        foreground="white", 
                        relief="flat",
                        font=("Segoe UI", 11, "bold"))
        style.map("Treeview", background=[("selected", selected_color)])
        style.map("Treeview.Heading", background=[('active', '#14375e')])

        tree_frame_app = ctk.CTkFrame(self.tab_app, fg_color="transparent")
        tree_frame_app.pack(fill=ctk.BOTH, expand=True, pady=(0, 10))
        
        columns = ("VchCode", "Voucher No", "Date", "Party Name", "Created By", "Prev Amount", "New Amount", "Appr. Count", "Status")
        self.tree_app = ttk.Treeview(tree_frame_app, columns=columns, show="headings", selectmode="extended")
        
        scroll_app = ttk.Scrollbar(tree_frame_app, orient=tk.VERTICAL, command=self.tree_app.yview)
        self.tree_app.configure(yscroll=scroll_app.set)
        
        self.tree_app.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_app.pack(side=tk.RIGHT, fill=tk.Y)
        
        act_frame_app = ctk.CTkFrame(self.tab_app, fg_color="transparent")
        act_frame_app.pack(fill=ctk.X)
        self.btn_cancel = ctk.CTkButton(act_frame_app, text="❌ Cancel Approval", command=self.cancel_approval, state="disabled", fg_color="#c0392b", hover_color="#e74c3c", font=ctk.CTkFont(size=14, weight="bold"), height=35)
        self.btn_cancel.pack(side=ctk.RIGHT, pady=5)

        t = self.tree_app
        t.heading("VchCode", text="VchCode")
        t.heading("Voucher No", text="🧾 No.")
        t.heading("Date", text="📅 Date")
        t.heading("Party Name", text="🏢 Party")
        t.heading("Created By", text="👤 By")
        t.heading("Prev Amount", text="⏳ Prev")
        t.heading("New Amount", text="💰 Amt")
        t.heading("Appr. Count", text="🔄")
        t.heading("Status", text="📌 Status")
        
        t.column("VchCode", width=0, stretch=tk.NO)
        t.column("Voucher No", width=80, anchor=tk.CENTER)
        t.column("Date", width=90, anchor=tk.CENTER)
        t.column("Party Name", width=150, anchor=tk.W)
        t.column("Created By", width=0, stretch=tk.NO)
        t.column("Prev Amount", width=0, stretch=tk.NO)
        t.column("New Amount", width=80, anchor=tk.E)
        t.column("Appr. Count", width=0, stretch=tk.NO)
        t.column("Status", width=80, anchor=tk.CENTER)
        
        # Bottom Status
        self.lbl_info = ctk.CTkLabel(self.root, text="", font=ctk.CTkFont(size=12), text_color="gray")
        self.lbl_info.pack(side=tk.BOTTOM, pady=10)
        
        self.update_lock_state()

        # Context Menus
        self.menu_app = tk.Menu(self.root, tearoff=0)
        self.menu_app.add_command(label="❌ Cancel Approval", command=self.cancel_approval)
        self.tree_app.bind("<Button-3>", self.show_context_menu_app)

    def show_context_menu_app(self, event):
        if self.is_locked:
            messagebox.showwarning("Locked", "Please unlock the application to perform this action.")
            return
        item = self.tree_app.identify_row(event.y)
        if item:
            if item not in self.tree_app.selection():
                self.tree_app.selection_set(item)
            self.menu_app.tk_popup(event.x_root, event.y_root)

    def toggle_lock(self):
        if self.is_locked:
            dialog = ctk.CTkInputDialog(text="Enter Password:", title="Unlock")
            pwd = dialog.get_input()
            if pwd == "1970":
                self.is_locked = False
                self.update_lock_state()
            elif pwd is not None:
                messagebox.showerror("Error", "Incorrect Password")
        else:
            self.is_locked = True
            self.update_lock_state()

    def update_lock_state(self):
        if self.is_locked:
            self.btn_lock.configure(text="🔒", fg_color="#e74c3c", hover_color="#c0392b")
            self.btn_approve.configure(state="disabled")
            self.btn_cancel.configure(state="disabled")
        else:
            self.btn_lock.configure(text="🔓", fg_color="#2ecc71", hover_color="#27ae60")
            if self.bfe_active:
                self.btn_approve.configure(state="normal")
                self.btn_cancel.configure(state="normal")

    def init_bfe(self):
        try:
            from bridge.connection import initialize_bfe, _get_rs
            from config import DATA_PATH, COMP_CODE, DB_PASSWORD
            initialize_bfe()
            self.get_rs_func = _get_rs
            self.bfe_active = True
            
            self.root.after(0, self.on_bfe_ready)
        except Exception as e:
            logging.error(f"BFE Initialization Error: {e}")
            self.root.after(0, lambda: self.lbl_status.configure(text=f"BFE Error: {e}", text_color="#e74c3c"))
            time.sleep(10)
            self.init_bfe()

    def on_bfe_ready(self):
        self.lbl_status.configure(text="✅ Connected to Busy", text_color="#2ecc71")
        self.btn_refresh.configure(state="normal")
        self.update_lock_state()
        self.refresh_data()
        self.schedule_refresh()

    def schedule_refresh(self):
        if self.bfe_active:
            self.refresh_data()
        self.root.after(INTERVAL_MS, self.schedule_refresh)

    def refresh_data(self):
        if not self.bfe_active or not self.get_rs_func:
            return
        if getattr(self, 'is_refreshing', False):
            return
        self.is_refreshing = True
        self.btn_refresh.configure(text="⏳", state="disabled")
        threading.Thread(target=self._fetch_data_thread, daemon=True).start()

    def _fetch_data_thread(self):
        try:
            today_date = datetime.date.today().strftime("%m/%d/%Y")
            sql = f"""
                SELECT t1.VchCode, t1.VchNo, t1.Date, t1.VchAmtBaseCur, c.UserName, c.ActionTime AS VchTime, m.Name AS MasterParty, bd.PartyName AS BillParty
                FROM (((Tran1 t1
                LEFT JOIN CheckList c ON (t1.VchCode = c.Code AND c.Type = 2 AND c.Action = 1))
                LEFT JOIN Master1 m ON t1.MasterCode1 = m.Code)
                LEFT JOIN BillingDet bd ON t1.VchCode = bd.VchCode)
                WHERE t1.VchType = 9 AND t1.Date = #{today_date}#
            """
            
            busy_vouchers = {}
            try:
                rs = self.get_rs_func(sql)
            except Exception as e:
                logging.error(f"BFE Connection Lost during fetch: {e}")
                self.bfe_active = False
                self.root.after(0, lambda: self.lbl_status.configure(text="❌ BFE Disconnected, Retrying...", text_color="#e74c3c"))
                threading.Thread(target=self.init_bfe, daemon=True).start()
                self.root.after(0, self._on_fetch_error)
                return

            def safe_val(field_name, default=""):
                try:
                    val = rs.Fields(field_name).Value
                    return val if val is not None else default
                except Exception:
                    return default

            while not rs.EOF:
                vcode = int(safe_val('VchCode', 0))
                vchno = str(safe_val('VchNo', "")).strip()
                raw_date = str(safe_val('Date', ""))[:10]
                if raw_date and "-" in raw_date:
                    parts = raw_date.split("-")
                    if len(parts) == 3:
                        raw_date = f"{parts[2]}-{parts[1]}-{parts[0]}"
                elif raw_date and "/" in raw_date:
                    parts = raw_date.split("/")
                    if len(parts) == 3:
                        raw_date = f"{parts[0]}-{parts[1]}-{parts[2]}"
                
                amt = float(safe_val('VchAmtBaseCur', 0))
                creator = str(safe_val('UserName', "Admin")).strip()
                vch_time = str(safe_val('VchTime', "")).strip()
                if vch_time:
                    raw_date = f"{raw_date} {vch_time}"
                
                master_party = str(safe_val('MasterParty', "")).strip()
                bill_party = str(safe_val('BillParty', "")).strip()
                party_name = bill_party if bill_party else master_party
                if not party_name:
                    party_name = "Unknown"
                
                busy_vouchers[vcode] = {"vchno": vchno, "date": raw_date, "party": party_name, "amount": amt, "creator": creator}
                rs.MoveNext()
            rs.Close()
            
            try:
                conn = sqlite3.connect(DB_PATH, timeout=5.0)
                c = conn.cursor()
                c.execute("SELECT vchcode, amount, status, previous_amount, approval_count FROM approvals")
                db_records = {row[0]: {"amount": row[1], "status": row[2], "prev": row[3] or 0, "count": row[4] or 0} for row in c.fetchall()}
                conn.close()
            except sqlite3.Error as e:
                logging.error(f"SQLite Read Error: {e}")
                db_records = {}
            
            unapproved = []
            approved = []
            
            for vcode, info in busy_vouchers.items():
                if vcode not in db_records:
                    unapproved.append((vcode, info["vchno"], info["date"], info["party"], info["creator"], "-", info["amount"], 0, "Unapproved"))
                else:
                    db_rec = db_records[vcode]
                    if db_rec["status"] == "APPROVED" and abs(db_rec["amount"] - info["amount"]) < 0.01:
                        prev_amt = db_rec["prev"] if db_rec["count"] > 1 else "-"
                        approved.append((vcode, info["vchno"], info["date"], info["party"], info["creator"], prev_amt, info["amount"], db_rec["count"], "Approved"))
                    elif db_rec["status"] != "APPROVED":
                        prev_amt = db_rec["prev"] if db_rec["count"] > 0 else "-"
                        unapproved.append((vcode, info["vchno"], info["date"], info["party"], info["creator"], prev_amt, info["amount"], db_rec["count"], "Unapproved"))
                    elif abs(db_rec["amount"] - info["amount"]) > 0.01:
                        unapproved.append((vcode, info["vchno"], info["date"], info["party"], info["creator"], db_rec["amount"], info["amount"], db_rec["count"], "Amount Changed"))
            
            self.root.after(0, lambda: self._update_ui(unapproved, approved))
        except Exception as e:
            logging.exception(f"Error fetching from Busy: {e}")
            self.root.after(0, self._on_fetch_error)
            
    def _on_fetch_error(self):
        self.is_refreshing = False
        if not self.is_locked:
            self.btn_refresh.configure(text="🔄", state="normal")
        else:
            self.btn_refresh.configure(text="🔄", state="disabled")

    def _update_ui(self, unapproved, approved):
        self.is_refreshing = False
        self.btn_refresh.configure(text="🔄", state="normal")
        
        self.lbl_info.configure(text=f"Last updated: {datetime.datetime.now().strftime('%H:%M:%S')}")
        
        current_unapp_hash = hash(str(unapproved))
        current_app_hash = hash(str(approved))
        
        if getattr(self, 'last_unapp_hash', None) != current_unapp_hash:
            self.unapproved_data = unapproved
            self.draw_cards(unapproved)
            self.last_unapp_hash = current_unapp_hash
            
        if getattr(self, 'last_app_hash', None) != current_app_hash:
            self.tree_app.delete(*self.tree_app.get_children())
            for i, item in enumerate(approved):
                self.tree_app.insert("", tk.END, values=item)
            self.last_app_hash = current_app_hash

        # Beep notification logic
        current_unapp_count = len(unapproved)
        current_time = time.time()
        
        should_beep = False
        if current_unapp_count > self.prev_unapproved_count:
            should_beep = True
        elif current_unapp_count > 0 and current_time - self.last_beep_time >= 60:
            should_beep = True
            
        if should_beep:
            try:
                winsound.PlaySound("SystemAsterisk", winsound.SND_ALIAS | winsound.SND_ASYNC)
            except Exception:
                pass
            self.last_beep_time = current_time
            
        self.prev_unapproved_count = current_unapp_count

    def draw_cards(self, unapproved_list):
        for widget in self.cards_frame.winfo_children():
            widget.destroy()
            
        if not unapproved_list:
            lbl = ctk.CTkLabel(self.cards_frame, text="🎉 No pending vouchers!", font=ctk.CTkFont(size=18, weight="bold"), text_color="gray")
            lbl.pack(pady=50)
            return
            
        for item in unapproved_list:
            vcode, vchno, vdate, party, creator, prev_amt, new_amt, count_val, status = item
            
            is_changed = (status == "Amount Changed")
            # CTk uses different fg_color depending on mode (light, dark). 
            # Provide a tuple for (light_color, dark_color)
            bg_color = ("#ffeaea", "#4a2c2c") if is_changed else ("#ffffff", "#2b2b2b")
            border_color = "#ff7675" if is_changed else ("#dcdcdc", "#3b3b3b")
            
            card = ctk.CTkFrame(self.cards_frame, fg_color=bg_color, border_color=border_color, border_width=2, corner_radius=12)
            card.pack(fill=ctk.X, pady=8, padx=10)
            
            # Left Info
            left_frame = ctk.CTkFrame(card, fg_color="transparent")
            left_frame.pack(side=ctk.LEFT, fill=ctk.BOTH, expand=True, padx=15, pady=12)
            
            top_row = ctk.CTkFrame(left_frame, fg_color="transparent")
            top_row.pack(fill=ctk.X)
            ctk.CTkLabel(top_row, text=f"🧾 {vchno}", font=ctk.CTkFont(size=12, weight="bold"), text_color="gray").pack(side=ctk.LEFT, padx=(0, 10))
            ctk.CTkLabel(top_row, text=f"📅 {vdate}", font=ctk.CTkFont(size=12), text_color="gray").pack(side=ctk.LEFT, padx=10)
            
            user_colors = {"ADMIN": "#e74c3c", "SHREYAS": "#2980b9", "GOPAL": "#8e44ad"}
            creator_color = user_colors.get(creator.upper(), ("#34495e", "#95a5a6"))
            ctk.CTkLabel(top_row, text=f"👤 {creator}", font=ctk.CTkFont(size=12, weight="bold"), text_color=creator_color).pack(side=ctk.LEFT, padx=10)
            
            if count_val > 0:
                ctk.CTkLabel(top_row, text=f"🔄: {count_val}", fg_color="#f39c12", text_color="white", corner_radius=6, font=ctk.CTkFont(size=11, weight="bold")).pack(side=ctk.LEFT, padx=10)
                
            ctk.CTkLabel(left_frame, text=f"🏢 {party}", font=ctk.CTkFont(size=16, weight="bold"), anchor="w", justify="left", wraplength=320).pack(fill=ctk.X, pady=8)
            
            bottom_row = ctk.CTkFrame(left_frame, fg_color="transparent")
            bottom_row.pack(fill=ctk.X)
            
            ctk.CTkLabel(bottom_row, text=f"💰 ₹{new_amt:,.2f}", font=ctk.CTkFont(size=18, weight="bold"), text_color="#2ecc71").pack(side=ctk.LEFT)
            
            if prev_amt != "-":
                ctk.CTkLabel(bottom_row, text=f" (Was: ₹{prev_amt:,.2f})", font=ctk.CTkFont(size=12), text_color="#e74c3c").pack(side=ctk.LEFT, padx=8)
                
            if is_changed:
                ctk.CTkLabel(bottom_row, text=" ⚠️ Changed", font=ctk.CTkFont(size=13, weight="bold"), text_color="#e74c3c").pack(side=ctk.LEFT, padx=8)
                
            # Right Action
            right_frame = ctk.CTkFrame(card, fg_color="transparent")
            right_frame.pack(side=ctk.RIGHT, fill=ctk.Y, padx=15, pady=12)
            
            btn = ctk.CTkButton(right_frame, text="✅ Approve", width=110, height=45, font=ctk.CTkFont(size=15, weight="bold"), fg_color="#2ecc71", hover_color="#27ae60", cursor="hand2")
            btn.pack(expand=True)
            btn.configure(command=lambda item_data=item: self.approve_single(item_data))

    def approve_single(self, item_data):
        if self.is_locked:
            messagebox.showwarning("Locked", "Please unlock the application to approve vouchers.")
            return
        vcode, vchno, vdate, party, creator, prev_amt, new_amt, count_val, status = item_data
        
        if not messagebox.askyesno("Confirm Approval", f"Are you sure you want to approve voucher {vchno} for ₹{new_amt:,.2f}?"):
            return
            
        self.btn_approve.configure(state="disabled")
        self.root.update_idletasks()
        
        try:
            conn = sqlite3.connect(DB_PATH, timeout=5.0)
            c = conn.cursor()
            now = datetime.datetime.now().isoformat()
            
            with conn:
                c.execute("SELECT approval_count FROM approvals WHERE vchcode=?", (vcode,))
                row = c.fetchone()
                
                if row:
                    new_count = (row[0] or 0) + 1
                    c.execute('''
                        UPDATE approvals SET amount=?, status=?, approved_at=?, previous_amount=amount, approval_count=?
                        WHERE vchcode=?
                    ''', (new_amt, "APPROVED", now, new_count, vcode))
                else:
                    c.execute('''
                        INSERT INTO approvals (vchcode, vchno, amount, status, approved_at, previous_amount, approval_count) 
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    ''', (vcode, vchno, new_amt, "APPROVED", now, 0, 1))
            logging.info(f"Approved voucher {vchno} ({vcode}) for {new_amt}")
        except sqlite3.Error as e:
            logging.error(f"DB Error in approve_single: {e}")
            messagebox.showerror("Database Error", f"Failed to approve voucher:\n{e}")
        finally:
            if 'conn' in locals() and conn:
                conn.close()
            self.update_lock_state()
            self.refresh_data()

    def approve_all(self):
        if self.is_locked:
            messagebox.showwarning("Locked", "Please unlock the application to approve vouchers.")
            return
        if not hasattr(self, 'unapproved_data') or not self.unapproved_data:
            messagebox.showinfo("Empty", "No pending vouchers to approve.")
            return
            
        if not messagebox.askyesno("Confirm", f"Approve all {len(self.unapproved_data)} pending voucher(s)?"):
            return
            
        self.btn_approve.configure(state="disabled", text="⏳ Processing...")
        self.root.update_idletasks()
            
        try:
            conn = sqlite3.connect(DB_PATH, timeout=5.0)
            c = conn.cursor()
            now = datetime.datetime.now().isoformat()
            count = 0
            
            with conn:
                for item in self.unapproved_data:
                    vcode, vchno, vdate, party, creator, prev_amt, new_amt, count_val, status = item
                    c.execute("SELECT approval_count FROM approvals WHERE vchcode=?", (vcode,))
                    row = c.fetchone()
                    
                    if row:
                        new_count = (row[0] or 0) + 1
                        c.execute('''
                            UPDATE approvals SET amount=?, status=?, approved_at=?, previous_amount=amount, approval_count=?
                            WHERE vchcode=?
                        ''', (new_amt, "APPROVED", now, new_count, vcode))
                    else:
                        c.execute('''
                            INSERT INTO approvals (vchcode, vchno, amount, status, approved_at, previous_amount, approval_count) 
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        ''', (vcode, vchno, new_amt, "APPROVED", now, 0, 1))
                    count += 1
            logging.info(f"Bulk approved {count} vouchers.")
            messagebox.showinfo("Success", f"Successfully approved {count} voucher(s).")
        except sqlite3.Error as e:
            logging.error(f"DB Error in approve_all: {e}")
            messagebox.showerror("Database Error", f"Failed to approve vouchers:\n{e}")
        finally:
            if 'conn' in locals() and conn:
                conn.close()
            self.btn_approve.configure(text="✅ Approve All")
            self.update_lock_state()
            self.refresh_data()

    def cancel_approval(self):
        if self.is_locked:
            messagebox.showwarning("Locked", "Please unlock the application to cancel approvals.")
            return
        selected_items = self.tree_app.selection()
        if not selected_items:
            messagebox.showinfo("Select", "Please select an approved voucher to cancel.")
            return
            
        if not messagebox.askyesno("Confirm", f"Are you sure you want to cancel approval for {len(selected_items)} voucher(s)?"):
            return
            
        self.btn_cancel.configure(state="disabled", text="⏳ Processing...")
        self.root.update_idletasks()
            
        try:
            conn = sqlite3.connect(DB_PATH, timeout=5.0)
            c = conn.cursor()
            vcodes = [(self.tree_app.item(item_id)['values'][0],) for item_id in selected_items]
            
            with conn:
                c.executemany("UPDATE approvals SET status='UNAPPROVED' WHERE vchcode=?", vcodes)
            
            logging.info(f"Cancelled approval for {len(vcodes)} vouchers.")
            messagebox.showinfo("Success", f"Approval cancelled for {len(vcodes)} voucher(s).")
        except sqlite3.Error as e:
            logging.error(f"DB Error in cancel_approval: {e}")
            messagebox.showerror("Database Error", f"Failed to cancel approvals:\n{e}")
        finally:
            if 'conn' in locals() and conn:
                conn.close()
            self.btn_cancel.configure(text="❌ Cancel Approval")
            self.update_lock_state()
            self.refresh_data()

if __name__ == "__main__":
    app = ctk.CTk()
    VoucherApprovalApp(app)
    app.mainloop()
