from app.db import get_connection


conn = get_connection()

cursor = conn.cursor()

cursor.execute("""
SELECT
    id,
    name,
    person_type,
    company,
    generated_message,
    status
FROM connections
""")

rows = cursor.fetchall()

for row in rows:
    print("\n--------------------")

    print("ID:", row[0])
    print("Name:", row[1])
    print("Type:", row[2])
    print("Company:", row[3])
    print("Message:", row[4])
    print("Status:", row[5])


conn.close()