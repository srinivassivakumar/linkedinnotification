import requests

token = "8834343192:AAHa_t5_SDBzLobCVrT4hYTvLFQDN4mkbL8"

base_url = f"https://api.telegram.org/bot{token}"

print("Testing URL:")
print(base_url)

# 1. Check bot identity
me = requests.get(f"{base_url}/getMe", timeout=30)
print("\nBOT:")
print(me.status_code)
print(me.text)

# 2. Check webhook
webhook = requests.get(f"{base_url}/getWebhookInfo", timeout=30)
print("\nWEBHOOK:")
print(webhook.status_code)
print(webhook.text)

# 3. Check updates
updates = requests.get(f"{base_url}/getUpdates", timeout=30)
print("\nUPDATES:")
print(updates.status_code)
print(updates.text)