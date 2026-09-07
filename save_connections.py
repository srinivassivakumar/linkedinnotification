import os
import base64

from dotenv import load_dotenv

from app.db import create_tables, get_connection
from app.services.gmail_service import get_gmail_service

from app.services.connection_repository import (
    save_connection,
)

from app.services.connection_processor import (
    process_and_send_for_approval,
)

from linkedin_email_parser import (
    parse_acceptance_email,
)


load_dotenv()


DEFAULT_GMAIL_QUERY = 'subject:"accepted your invitation"'

GMAIL_QUERY = os.getenv(
    "GMAIL_QUERY",
    DEFAULT_GMAIL_QUERY
).strip()

LABEL_NAME = os.getenv(
    "GMAIL_LABEL",
    ""
).strip()

USE_LABEL = os.getenv(
    "GMAIL_USE_LABEL",
    "false"
).strip().lower() in {
    "1",
    "true",
    "yes",
    "on"
}

MAX_RESULTS = int(
    os.getenv(
        "GMAIL_MAX_RESULTS",
        "50"
    )
)


def decode_base64url(data):
    if not data:
        return ""

    data += "=" * (-len(data) % 4)

    return base64.urlsafe_b64decode(
        data.encode("utf-8")
    ).decode(
        "utf-8",
        errors="ignore"
    )


def extract_html(payload):
    if payload.get("mimeType") == "text/html":
        data = payload.get(
            "body",
            {}
        ).get("data")

        if data:
            return decode_base64url(data)

    for part in payload.get("parts", []):
        result = extract_html(part)

        if result:
            return result

    return ""


def get_header(headers, name):
    for header in headers:
        if header["name"].lower() == name.lower():
            return header["value"]

    return None


def sender_name_from_header(sender):
    if not sender:
        return None

    return sender.split("<")[0].strip()


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


def list_candidate_messages(service):
    list_kwargs = {
        "userId": "me",
        "maxResults": min(MAX_RESULTS, 500)
    }

    if GMAIL_QUERY:
        list_kwargs["q"] = GMAIL_QUERY
        print(f"Gmail search query: {GMAIL_QUERY}")

    elif LABEL_NAME:
        print(f"Gmail label: {LABEL_NAME}")

    else:
        raise RuntimeError(
            "Set GMAIL_QUERY or GMAIL_LABEL in .env."
        )

    if USE_LABEL and LABEL_NAME:
        label_id = get_label_id(
            service,
            LABEL_NAME
        )

        if not label_id:
            raise RuntimeError(
                f"Gmail label '{LABEL_NAME}' not found"
            )

        list_kwargs["labelIds"] = [
            label_id
        ]

        print(f"Filtering by label: {LABEL_NAME}")

    messages = []
    page_token = None

    while len(messages) < MAX_RESULTS:
        if page_token:
            list_kwargs["pageToken"] = page_token
        elif "pageToken" in list_kwargs:
            del list_kwargs["pageToken"]

        response = service.users().messages().list(
            **list_kwargs
        ).execute()

        messages.extend(
            response.get(
                "messages",
                []
            )
        )

        page_token = response.get(
            "nextPageToken"
        )

        if not page_token:
            break

    return messages[:MAX_RESULTS]


def message_already_processed(gmail_message_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id
        FROM processed_emails
        WHERE gmail_message_id = ?
        """,
        (
            gmail_message_id,
        )
    )

    exists = (
        cursor.fetchone()
        is not None
    )

    conn.close()

    return exists


def mark_processed(gmail_message_id):
    conn = get_connection()
    cursor = conn.cursor()

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

    conn.commit()
    conn.close()


def attach_gmail_message_id(connection_id, gmail_message_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE connections
        SET gmail_message_id = ?
        WHERE id = ?
        """,
        (
            gmail_message_id,
            connection_id
        )
    )

    conn.commit()
    conn.close()


def get_connection_id_by_gmail_message_id(gmail_message_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id
        FROM connections
        WHERE gmail_message_id = ?
        """,
        (
            gmail_message_id,
        )
    )

    row = cursor.fetchone()
    conn.close()

    if row is None:
        return None

    return row[0]


def main():
    create_tables()

    service = get_gmail_service()
    messages = list_candidate_messages(service)

    print(
        f"Found {len(messages)} "
        "candidate emails"
    )

    new_count = 0
    skipped_count = 0
    failed_count = 0

    for item in messages:
        gmail_message_id = item["id"]

        if message_already_processed(
            gmail_message_id
        ):
            print(
                f"Already processed: "
                f"{gmail_message_id}"
            )

            skipped_count += 1
            continue

        print()
        print("=" * 60)

        print(
            "Processing Gmail message:",
            gmail_message_id
        )

        try:
            msg = (
                service.users()
                .messages()
                .get(
                    userId="me",
                    id=gmail_message_id,
                    format="full"
                )
                .execute()
            )

            payload = msg.get(
                "payload",
                {}
            )

            headers = payload.get(
                "headers",
                []
            )

            sender = get_header(
                headers,
                "From"
            )

            sender_name = (
                sender_name_from_header(
                    sender
                )
            )

            html = extract_html(
                payload
            )

            if not html:
                print(
                    "No HTML found. "
                    "Skipping."
                )

                failed_count += 1
                continue

            parsed = (
                parse_acceptance_email(
                    html,
                    sender_name
                )
            )

            print(
                "Name:",
                parsed.get("name")
            )

            print(
                "Headline:",
                parsed.get("headline")
            )

            print(
                "LinkedIn:",
                parsed.get(
                    "linkedin_profile_url"
                )
            )

            if not parsed.get("name"):
                print(
                    "Could not determine name."
                )

                failed_count += 1
                continue

            if not parsed.get(
                "linkedin_profile_url"
            ):
                print(
                    "Could not determine "
                    "LinkedIn profile URL."
                )

                failed_count += 1
                continue

            person = {
                "name":
                    parsed.get("name"),

                "current_title":
                    parsed.get("headline"),

                "linkedin_url":
                    parsed.get(
                        "linkedin_profile_url"
                    ),
            }

            connection_id = (
                get_connection_id_by_gmail_message_id(
                    gmail_message_id
                )
            )

            if connection_id is None:
                connection_id = (
                    save_connection(
                        person
                    )
                )

                attach_gmail_message_id(
                    connection_id,
                    gmail_message_id
                )

                print(
                    "Saved connection ID:",
                    connection_id
                )

            else:
                print(
                    "Reusing connection ID:",
                    connection_id
                )

            processing_result = (
                process_and_send_for_approval(
                    connection_id,
                    person
                )
            )

            mark_processed(
                gmail_message_id
            )

            new_count += 1

            print()
            print(
                "Completed:",
                parsed.get("name")
            )

            print(
                "Result type:",
                processing_result.get(
                    "type"
                )
            )

        except Exception as e:
            failed_count += 1

            print(
                "Processing failed:"
            )

            print(
                type(e).__name__,
                str(e)
            )

    print()
    print("=" * 60)
    print("Finished")
    print("=" * 60)

    print(
        "New:",
        new_count
    )

    print(
        "Skipped:",
        skipped_count
    )

    print(
        "Failed:",
        failed_count
    )


if __name__ == "__main__":
    main()
