from app.db import get_connection
from app.services.telegram_service import send_approval_card


def get_connection_by_id(connection_id):

    conn = get_connection()

    conn.row_factory = __import__("sqlite3").Row

    cursor = conn.cursor()

    cursor.execute("""
    SELECT *
    FROM connections
    WHERE id = ?
    """, (connection_id,))

    row = cursor.fetchone()

    conn.close()

    if row is None:
        return None

    return dict(row)


connection = get_connection_by_id(1)


if connection is None:
    print("Connection not found.")

else:
    print("Sending Telegram approval card for:")
    print(connection["name"])

    result = send_approval_card(connection)

    print("Telegram response OK:")
    print(result.get("ok"))