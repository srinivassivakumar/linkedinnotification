import requests

token = "8834343192:AAHa_t5_SDBzLobCVrT4hYTvLFQDN4mkbL8"

url = f"https://api.telegram.org/bot{token}/getUpdates"

response = requests.get(url, timeout=30)

print(response.json())