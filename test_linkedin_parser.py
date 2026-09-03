import base64

from app.services.gmail_service import get_gmail_service
from linkedin_email_parser import parse_acceptance_email

LABEL_NAME = "LinkedInAccepted"


def decode_base64url(data):
    """
    Decode Gmail's base64-url encoded email body.
    """
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
    """
    Recursively search Gmail message parts
    and return the HTML body.
    """

    mime_type = payload.get("mimeType", "")

    if mime_type == "text/html":
        data = payload.get("body", {}).get("data")

        if data:
            return decode_base64url(data)

    for part in payload.get("parts", []):
        result = extract_html(part)

        if result:
            return result

    return ""


def get_header(headers, name):
    """
    Get a specific Gmail header such as
    From or Subject.
    """

    for header in headers:
        if header["name"].lower() == name.lower():
            return header["value"]

    return None


def sender_name_from_header(sender):
    """
    Example:

    Abhijeet Phadnis via LinkedIn <invitations@linkedin.com>

    becomes:

    Abhijeet Phadnis via LinkedIn
    """

    if not sender:
        return None

    return sender.split("<")[0].strip()


def get_label_id(service, label_name):
    """
    Find Gmail label ID from label name.
    """

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

    print("Connecting to Gmail...")

    service = get_gmail_service()

    print("✅ Gmail connected")

    label_id = get_label_id(
        service,
        LABEL_NAME
    )

    if not label_id:
        raise RuntimeError(
            f"Gmail label '{LABEL_NAME}' was not found."
        )

    print(
        f"✅ Label found: {label_id}"
    )

    result = service.users().messages().list(
        userId="me",
        labelIds=[label_id],
        maxResults=20
    ).execute()

    messages = result.get(
        "messages",
        []
    )

    print(
        f"Found {len(messages)} LinkedIn acceptance emails"
    )

    if not messages:
        print(
            "No emails found with LinkedInAccepted label."
        )
        return

    for item in messages:

        gmail_message_id = item["id"]

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

        subject = get_header(
            headers,
            "Subject"
        )

        sender_name = sender_name_from_header(
            sender
        )

        html = extract_html(
            payload
        )

        if not html:
            print(
                "\n⚠️ No HTML body found for:",
                gmail_message_id
            )
            continue

        parsed = parse_acceptance_email(
            html,
            sender_name
        )

        print("\n" + "=" * 70)

        print(
            "Gmail ID:",
            gmail_message_id
        )

        print(
            "Subject:",
            subject
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
            "Location:",
            parsed.get("location")
        )

        print(
            "LinkedIn profile:",
            parsed.get(
                "linkedin_profile_url"
            )
        )

        print(
            "LinkedIn message:",
            parsed.get(
                "linkedin_message_url"
            )
        )

    print("\n✅ Parsing test complete")


if __name__ == "__main__":
    main()