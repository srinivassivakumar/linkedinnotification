import os
import sqlite3
from dotenv import load_dotenv

load_dotenv()

database_url = os.getenv("DATABASE_URL")

if not database_url:
    raise ValueError("DATABASE_URL missing from .env")

# sqlite:///data/assistant.db -> data/assistant.db
db_path = database_url.replace("sqlite:///", "")

os.makedirs(os.path.dirname(db_path), exist_ok=True)

conn = sqlite3.connect(db_path)

cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS connections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    linkedin_url TEXT,
    person_type TEXT,
    current_title TEXT,
    company TEXT,
    company_summary TEXT,

    job_title TEXT,
    job_url TEXT,
    required_experience TEXT,
    job_match_score INTEGER,

    generated_message TEXT,

    status TEXT DEFAULT 'pending',

    gmail_message_id TEXT UNIQUE,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    approved_at TIMESTAMP
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS processed_emails (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    gmail_message_id TEXT UNIQUE NOT NULL,
    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

conn.commit()
conn.close()

print(f"✅ Database initialized successfully at: {db_path}")