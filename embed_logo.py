with open(r'C:\Users\GOPAL MARKETING\Desktop\BUSY\receipt_app\static\logo_b64.txt', 'r') as f:
    logo_b64 = f.read().strip()

with open(r'C:\Users\GOPAL MARKETING\Desktop\BUSY\receipt_app\templates\ledger_whatsapp.html', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace('LOGO_PLACEHOLDER', logo_b64)

with open(r'C:\Users\GOPAL MARKETING\Desktop\BUSY\receipt_app\templates\ledger_whatsapp.html', 'w', encoding='utf-8') as f:
    f.write(content)

print('Ledger logo embedded! File size:', len(content))
