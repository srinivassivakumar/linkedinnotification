import os
import base64

from dotenv import load_dotenv

from app.services.gmail_service import get_gmail_service
from app.services.connection_repository import save_connection
from app.services.connection_processor import process_and_send_for_approval
from app.db import get_connection

from linkedin_email_parser import parse_acceptance_email


load_dotenv()

LABEL_NAME = os.getenv(
    "GMAIL_LABEL",
    "LinkedInAccepted"
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


def attach_gmail_message_id(
    connection_id,
    gmail_message_id
):

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


def main():

    service = get_gmail_service()

    label_id = get_label_id(
        service,
        LABEL_NAME
    )

    if not label_id:
        raise RuntimeError(
            f"Label '{LABEL_NAME}' not found"
        )


    result = service.users().messages().list(
        userId="me",
        labelIds=[label_id],
        maxResults=10
    ).execute()


    messages = result.get(
        "messages",
        []
    )


    if not messages:
        print("No labeled LinkedIn emails found.")
        return


    # Use only the newest email
    gmail_message_id = messages[0]["id"]


    print(
        "Testing Gmail message:",
        gmail_message_id
    )


    msg = service.users().messages().get(
        userId="me",
        id=gmail_message_id,
        format="full"
    ).execute()


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

    sender_name = sender_name_from_header(
        sender
    )


    html = extract_html(
        payload
    )


    parsed = parse_acceptance_email(
        html,
        sender_name
    )


    print()
    print("Parsed connection")
    print("------------------")

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
        raise RuntimeError(
            "Name could not be parsed."
        )


    if not parsed.get(
        "linkedin_profile_url"
    ):
        raise RuntimeError(
            "LinkedIn URL could not be parsed."
        )


    person = {
        "name":
            parsed.get("name"),

        "current_title":
            parsed.get("headline"),

        "linkedin_url":
            parsed.get(
                "linkedin_profile_url"
            )
    }


    connection_id = save_connection(
        person
    )


    attach_gmail_message_id(
        connection_id,
        gmail_message_id
    )


    print()
    print(
        "Saved as connection ID:",
        connection_id
    )


    result = process_and_send_for_approval(
        connection_id,
        person
    )


    print()
    print("=" * 60)
    print("FINAL RESULT")
    print("=" * 60)

    print(result)


if __name__ == "__main__":
    main()