import os

from dotenv import load_dotenv

from app.db import get_connection
from app.services.gmail_service import get_gmail_service


load_dotenv()


LABEL_NAME = os.getenv(
    "GMAIL_LABEL",
    "LinkedInAccepted"
)


def get_label_id(service, label_name):

    labels = service.users().labels().list(
        userId="me"
    ).execute().get(
        "labels",
        []
    )

    for label in labels:

        if label["name"] == label_name:
            return label["id"]

    return None


def main():

    service = get_gmail_service()

    label_id = get_label_id(
        service,
        LABEL_NAME
    )

    if not label_id:
        raise RuntimeError(
            f"Gmail label '{LABEL_NAME}' not found"
        )


    result = service.users().messages().list(
        userId="me",
        labelIds=[label_id],
        maxResults=100
    ).execute()


    messages = result.get(
        "messages",
        []
    )


    print(
        f"Found {len(messages)} existing "
        f"LinkedIn acceptance emails."
    )


    conn = get_connection()
    cursor = conn.cursor()


    added = 0

    for item in messages:

        gmail_message_id = item["id"]

        cursor.execute(
            """
            INSERT OR IGNORE INTO processed_emails (
                gmail_message_id
            )
            VALUES (?)
            """,
            (
                gmail_message_id,
            )
        )

        if cursor.rowcount > 0:
            added += 1


    conn.commit()
    conn.close()


    print()
    print("Historical emails marked processed.")
    print("Added:", added)
    print()
    print(
        "Future Gmail worker runs will only "
        "process NEW acceptance emails."
    )


if __name__ == "__main__":
    main()