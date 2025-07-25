# whatsapp_sender.py
from twilio.rest import Client
import os
import streamlit as st

def send_whatsapp(message, to_number="+91xxxxxxxxxx"):
    account_sid = st.secrets["TWILIO_SID"]
    auth_token = st.secrets["TWILIO_AUTH"]
    client = Client(account_sid, auth_token)

    from_whatsapp = 'whatsapp:+14155238886'  # Twilio sandbox
    to_whatsapp = f'whatsapp:{to_number}'

    client.messages.create(body=message, from_=from_whatsapp, to=to_whatsapp)

def send_whatsapp_with_pdf(message, pdf_bytes, filename, to_number="+91xxxxxxxxxx"):
    from twilio.rest import Client
    import os

    from_whatsapp = 'whatsapp:+14155238886'
    to_whatsapp = f'whatsapp:{to_number}'
    account_sid = "ACe147a625e2fac891b21dd0bd1799a586"
    auth_token = "243ec094e46bb5e17ba16a1d8a2f6fd0"
    client = Client(account_sid, auth_token)

    # ✅ Decode only if filename is bytes
    if isinstance(filename, bytes):
        filename = filename.decode()

    # Save PDF temporarily
    os.makedirs("temp", exist_ok=True)
    temp_path = os.path.join("temp", filename)
    with open(temp_path, "wb") as f:
        f.write(pdf_bytes)

    # ⚠️ Twilio media support needs public URL – this is a placeholder
    print(f"🟡 PDF saved at: {temp_path} (Twilio needs public media URL)")

    # Send WhatsApp message (text only, no real attachment)
    client.messages.create(
        body=message + "\n\n(PDF saved locally)",
        from_=from_whatsapp,
        to=to_whatsapp
    )




# Usage:
# send_whatsapp("Your banana report is ready!", "+91XXXXXXXXXX")

