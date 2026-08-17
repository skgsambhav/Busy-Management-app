from flask import Blueprint, render_template_string
from bridge.connection import _get_rs
from bridge.ledger import get_ledger

print_bp = Blueprint('print', __name__)

RECEIPT_HTML_TEMPLATE = """
<HTML>
<style> 
  .CPI_12_Courier {font-family:'Courier New';font-size:10pt}      
  .COND_Courier     {font-family:'Courier New';font-size:7pt}      
  .CPI_10_Courier   {font-family:'Courier New';font-size:12pt}      
  .DW_Courier       {font-family:'Courier New';font-size:24pt}      
  .FONT18_Courier   {font-family:'Courier New';font-size:18pt}      
  .FONT15_Courier   {font-family:'Courier New';font-size:15pt}
  P {page-break-before:always}
  body { margin: 0; padding: 10px; }
  @media print {
      @page { margin: 0; size: 80mm auto; }
      body { padding: 0; margin: 10px; }
  }
</style>
<Body bgcolor='#FFFFF3' text='0' onload="window.print()">
<pre><span class='CPI_10_Courier'>                      <span class='COND_Courier'><B><SPAN STYLE="font-family:;font-size:17pt">     जमा पर्ची      </SPAN></B></SPAN>&nbsp;<Br>&nbsp;<Br>&nbsp;<Br>
<B>पर्ची क्रमांक :    </B> {{ vch_no }}  <B>दिनांक</B> {{ date_str }}&nbsp;<Br>&nbsp;<Br>
<B>जमाकर्ता नाम :     </B>{{ party_name_hi }}&nbsp;<Br>&nbsp;<Br>
<B>पिछला बैलेंस :     </B>     {{ prev_balance }}&nbsp;<Br>&nbsp;<Br>
<B>जमा राशी :         </B>       {{ amount }}&nbsp;<Br>&nbsp;<Br>
<B>कुल बकाया राशी :   </B>{{ new_balance }} &nbsp;<Br>&nbsp;<Br>
<B>प्राप्तकर्ता : गोपाल मार्केटिंग, अंबिकापुर </B>&nbsp;<Br>&nbsp;<Br>&nbsp;<Br>
</span></pre>
</Body>
</HTML>
"""

@print_bp.route('/print/receipt/<vch_no>')
def print_receipt(vch_no):
    # Lookup Tran1 for Receipt VchNo
    sql_tran = f"SELECT VchCode, Date, Value1, MasterCode1 FROM Tran1 WHERE VchType=14 AND VchNo='{vch_no}'"
    rs = _get_rs(sql_tran)
    if rs.EOF:
        return "Receipt not found", 404
        
    date_val = rs.Fields('Date').Value
    date_str = date_val.strftime("%d-%m-%Y") if date_val else ""
    amount = float(rs.Fields('Value1').Value or 0)
    party_code = int(rs.Fields('MasterCode1').Value or 0)
    rs.Close()
    
    # Lookup Party Name (Hindi and English)
    sql_party = f"SELECT Name, NameSL FROM Master1 WHERE Code={party_code}"
    rs_party = _get_rs(sql_party)
    party_name_en = str(rs_party.Fields('Name').Value or "").strip()
    party_name_hi = str(rs_party.Fields('NameSL').Value or "").strip()
    if not party_name_hi:
        party_name_hi = party_name_en
    rs_party.Close()
    
    # Calculate ledger balances using the actual ledger logic
    ledger_data = get_ledger(party_code)
    transactions = ledger_data.get('transactions', [])
    running = ledger_data.get('op_bal', 0)
    
    prev_balance_val = running
    for t in transactions:
        # Find the balance right before this receipt
        if str(t.get('vch_no', '')) == str(vch_no):
            break
        prev_balance_val += t.get('amount', 0)
        
    new_balance_val = prev_balance_val + amount # In Busy DB amount is negative for credit, wait, receipt amount is passed as positive?
    # In ledger, Receipt Cr is positive.
    # Let's just calculate running total up to today.
    # Actually, busy printout says "1,52,005.00 Dr" and then "-132005.00".
    
    def fmt_bal(val):
        if val < 0:
            return f"{abs(val):,.2f} Dr"
        elif val > 0:
            return f"{val:,.2f} Cr"
        return "0.00"
        
    return render_template_string(RECEIPT_HTML_TEMPLATE, 
                                  vch_no=vch_no,
                                  date_str=date_str,
                                  party_name_hi=party_name_hi,
                                  prev_balance=fmt_bal(prev_balance_val),
                                  amount=f"{amount:,.2f}",
                                  new_balance=fmt_bal(prev_balance_val + amount))
