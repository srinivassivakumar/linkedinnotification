from app.services.telegram_service import (
    get_updates,
    answer_callback_query,
    send_message
)

from app.services.connection_repository import (
    update_connection_status,
    get_connection_by_id
)


print("Telegram callback worker started.")
print("Press Ctrl+C to stop.")


offset = None


while True:

    updates = get_updates(offset)

    for update in updates.get("result", []):

        offset = update["update_id"] + 1

        callback = update.get("callback_query")

        if not callback:
            continue

        callback_id = callback["id"]
        data = callback.get("data", "")

        print("Callback received:", data)


        try:
            action, connection_id = data.split(":")
            connection_id = int(connection_id)

        except ValueError:

            answer_callback_query(
                callback_id,
                "Invalid callback."
            )

            continue


        connection = get_connection_by_id(connection_id)


        if connection is None:

            answer_callback_query(
                callback_id,
                "Connection not found."
            )

            continue


        if action == "approve":

            update_connection_status(
                connection_id,
                "approved"
            )

            answer_callback_query(
                callback_id,
                "Approved ✅"
            )

            generated_message = connection.get(
                "generated_message"
            )

            linkedin_url = connection.get(
                "linkedin_url"
            )

            final_text = (
                f"✅ APPROVED\n\n"
                f"{connection['name']}\n\n"
                f"Final message:\n\n"
                f"{generated_message}"
            )

            buttons = []

            if linkedin_url:
                buttons.append([
                    {
                        "text": "💬 OPEN LINKEDIN",
                        "url": linkedin_url
                    }
                ])

            send_message(
                final_text,
                buttons=buttons
            )

            print(
                f"Connection {connection_id} approved."
            )


        elif action == "skip":

            update_connection_status(
                connection_id,
                "skipped"
            )

            answer_callback_query(
                callback_id,
                "Skipped ❌"
            )

            send_message(
                f"❌ Skipped {connection['name']}"
            )

            print(
                f"Connection {connection_id} skipped."
            )


        else:

            answer_callback_query(
                callback_id,
                "Unknown action."
            )