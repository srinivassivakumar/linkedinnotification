import os
import sqlite3
from pathlib import Path

from dotenv import load_dotenv


BASE = Path(__file__).resolve().parents[1]
load_dotenv(BASE / ".env")


def get_db_path():
    database_url = os.getenv(
        "DATABASE_URL",
        "sqlite:///data/linkedin_assistant.db"
    )

    if not database_url.startswith("sqlite:///"):
        raise ValueError(
            "Only sqlite:/// DATABASE_URL values are supported."
        )

    raw_path = database_url.replace("sqlite:///", "", 1)
    db_path = Path(raw_path)

    if not db_path.is_absolute():
        db_path = BASE / db_path

    db_path.parent.mkdir(parents=True, exist_ok=True)

    return db_path


DB_PATH = get_db_path()


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

    migrate_connections_table(cursor)

    conn.commit()
    conn.close()


def migrate_connections_table(cursor):
    cursor.execute("PRAGMA table_info(connections)")

    existing_columns = {
        row[1]
        for row in cursor.fetchall()
    }

    required_columns = {
        "company_url": "TEXT",
        "approved_at": "TIMESTAMP",
    }

    for column_name, column_type in required_columns.items():
        if column_name not in existing_columns:
            cursor.execute(
                f"ALTER TABLE connections "
                f"ADD COLUMN {column_name} {column_type}"
            )


if __name__ == "__main__":
    create_tables()
    print("Database created successfully.")
    print(f"Database location: {DB_PATH}")
