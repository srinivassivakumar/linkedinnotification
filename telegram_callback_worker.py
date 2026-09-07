import time

from app.db import create_tables

from app.services.telegram_service import (
    get_updates,
    answer_callback_query,
    send_message
)

from app.services.connection_repository import (
    update_connection_status,
    get_connection_by_id
)


def handle_callback(callback):
    callback_id = callback["id"]
    data = callback.get("data", "")

    print("Callback received:", data, flush=True)

    try:
        action, connection_id = data.split(":")
        connection_id = int(connection_id)

    except ValueError:
        answer_callback_query(
            callback_id,
            "Invalid callback."
        )
        return

    connection = get_connection_by_id(connection_id)

    if connection is None:
        answer_callback_query(
            callback_id,
            "Connection not found."
        )
        return

    if action == "approve":
        update_connection_status(
            connection_id,
            "approved"
        )

        answer_callback_query(
            callback_id,
            "Approved"
        )

        generated_message = connection.get(
            "generated_message"
        )

        linkedin_url = connection.get(
            "linkedin_url"
        )

        final_text = (
            "APPROVED\n\n"
            f"{connection['name']}\n\n"
            "Final message:\n\n"
            f"{generated_message}"
        )

        buttons = []

        if linkedin_url:
            buttons.append([
                {
                    "text": "OPEN LINKEDIN",
                    "url": linkedin_url
                }
            ])

        send_message(
            final_text,
            buttons=buttons
        )

        print(
            f"Connection {connection_id} approved.",
            flush=True
        )

    elif action == "skip":
        update_connection_status(
            connection_id,
            "skipped"
        )

        answer_callback_query(
            callback_id,
            "Skipped"
        )

        send_message(
            f"Skipped {connection['name']}"
        )

        print(
            f"Connection {connection_id} skipped.",
            flush=True
        )

    else:
        answer_callback_query(
            callback_id,
            "Unknown action."
        )


def main():
    create_tables()

    print("Telegram callback worker started.", flush=True)
    print("Press Ctrl+C to stop.", flush=True)

    offset = None

    while True:
        try:
            updates = get_updates(offset)

            for update in updates.get("result", []):
                offset = update["update_id"] + 1

                callback = update.get("callback_query")

                if not callback:
                    continue

                handle_callback(callback)

        except KeyboardInterrupt:
            print()
            print("Telegram callback worker stopped.", flush=True)
            break

        except Exception as e:
            print()
            print("Telegram polling failed:", flush=True)
            print(type(e).__name__, str(e), flush=True)
            print("Retrying in 15 seconds...", flush=True)
            time.sleep(15)


if __name__ == "__main__":
    main()
