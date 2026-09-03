import sqlite3
from pathlib import Path


BASE = Path(__file__).resolve().parents[1]

DATA_DIR = BASE / "data"
DATA_DIR.mkdir(exist_ok=True)

DB_PATH = DATA_DIR / "linkedin_assistant.db"


def get_connection():
    return sqlite3.connect(DB_PATH)


def create_tables():

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS connections (

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        name TEXT NOT NULL,

        current_title TEXT,

        linkedin_url TEXT,

        person_type TEXT,

        company TEXT,

        company_summary TEXT,

        company_url TEXT,

        job_title TEXT,

        job_url TEXT,

        required_experience TEXT,

        job_match_score REAL,

        generated_message TEXT,

        status TEXT DEFAULT 'pending',

        gmail_message_id TEXT UNIQUE,

        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

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


if __name__ == "__main__":

    create_tables()

    print("Database created successfully.")
    print(f"Database location: {DB_PATH}")