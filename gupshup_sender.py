# gupshup_sender.py
import requests

# Hybrid mapping (static + dynamic fallback)
CUSTOMER_WHATSAPP_MAP = {
    "os1": "+919008030624",
    "badri": "+917989502914",
    "os2": "+919505134645"
    # Add more if needed
}

GUPSHUP_API_KEY = "hzae5wibtyrailxmx1opl6dzawwgtgbn"
GUPSHUP_SENDER = "917834811114"
GUPSHUP_BOTNAME = "MRBusinessbot"

def send_gupshup_whatsapp(customer_name: str, message: str, fallback_number: str = ""):
    # Hybrid logic
    to_number = CUSTOMER_WHATSAPP_MAP.get(customer_name.lower(), fallback_number)
    if not to_number:
        print("❌ No number found for:", customer_name)
        return

    payload = {
        "channel": "whatsapp",
        "source": GUPSHUP_SENDER,
        "destination": to_number.replace("+", ""),
        "message": f'{{"type":"text","text":"{message}"}}',
        "src.name": GUPSHUP_BOTNAME
    }

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "apikey": GUPSHUP_API_KEY,
        "Cache-Control": "no-cache"
    }

    response = requests.post("https://api.gupshup.io/wa/api/v1/msg", data=payload, headers=headers)
    print("✅ Gupshup Status:", response.status_code)
    print("🔁 Gupshup Response:", response.text)


# 🔽 Test it
send_gupshup_whatsapp("badri", "Hello! Your banana shop payment summary . 🍌")
