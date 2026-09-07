from app.db import DB_PATH, create_tables


create_tables()

print(f"Database initialized successfully at: {DB_PATH}")
