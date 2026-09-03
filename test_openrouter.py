import os
import requests
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("OPENROUTER_API_KEY")
model = os.getenv("OPENROUTER_MODEL")

if not api_key:
    raise ValueError("OPENROUTER_API_KEY missing from .env")

if not model:
    raise ValueError("OPENROUTER_MODEL missing from .env")

url = "https://openrouter.ai/api/v1/chat/completions"

headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json"
}

payload = {
    "model": model,
    "messages": [
        {
            "role": "system",
            "content": "You are a concise professional networking assistant."
        },
        {
            "role": "user",
            "content": (
                "Write a short LinkedIn message to a startup founder. "
                "My skills are Python, AWS, RAG, LLMs, Docker, MLOps and data engineering. "
                "Maximum 50 words."
            )
        }
    ]
}

response = requests.post(
    url,
    headers=headers,
    json=payload,
    timeout=60
)

print("Status:", response.status_code)
print(response.text)