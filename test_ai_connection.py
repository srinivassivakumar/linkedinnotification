import os
import sqlite3

from dotenv import load_dotenv

from app.services.openrouter_service import analyze_connection


load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite:///data/assistant.db"
)

db_path = DATABASE_URL.replace(
    "sqlite:///",
    ""
)


conn = sqlite3.connect(db_path)

conn.row_factory = sqlite3.Row

cursor = conn.cursor()


cursor.execute("""
SELECT
    id,
    name,
    current_title,
    linkedin_url,
    status
FROM connections
WHERE status = 'pending'
ORDER BY id ASC
LIMIT 1
""")


person = cursor.fetchone()


if not person:
    print("No pending connections found.")
    conn.close()
    raise SystemExit


print("Testing connection:")
print("Name:", person["name"])
print("Headline:", person["current_title"])
print("LinkedIn:", person["linkedin_url"])

print("\nSending to OpenRouter...")


result = analyze_connection(
    name=person["name"],
    headline=person["current_title"],
    linkedin_url=person["linkedin_url"]
)


print("\n==============================")
print("AI RESULT")
print("==============================")

print("Person type:", result.get("person_type"))
print("Company:", result.get("company"))
print("Reason:", result.get("reason"))

print("\nGenerated message:")
print(result.get("message"))


conn.close()