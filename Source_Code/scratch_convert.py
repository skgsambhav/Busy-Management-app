from PIL import Image

# Open the image
img = Image.open(r"C:\Users\GOPAL MARKETING\.gemini\antigravity-ide\brain\c858e0d9-4c78-4b86-9418-7f3e3d678e05\gopal_marketing_logo_1787911551750.jpg")

# Resize the image to make a proper square icon
img = img.resize((256, 256), Image.Resampling.LANCZOS)

# Save as .ico
img.save(r"C:\Users\GOPAL MARKETING\Desktop\BUSY\receipt_app\icon.ico", format="ICO", sizes=[(256, 256)])
print("Conversion successful.")
