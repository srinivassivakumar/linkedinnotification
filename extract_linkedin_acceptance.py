import base64
import re
from bs4 import BeautifulSoup

from app.services.gmail_service import get_gmail_service


LABEL_NAME = "LinkedInAccepted"


def decode_base64url(data):
    if not data:
        return ""

    data += "=" * (-len(data) % 4)

    return base64.urlsafe_b64decode(
        data.encode("utf-8")
    ).decode("utf-8", errors="ignore")


def extract_body(payload):
    """
    Recursively extract HTML/text body from Gmail payload.
    """

    mime_type = payload.get("mimeType", "")

    body_data = payload.get("body", {}).get("data")

    if body_data and mime_type in ["text/html", "text/plain"]:
        return decode_base64url(body_data)

    for part in payload.get("parts", []):
        content = extract_body(part)

        if content:
            # Prefer HTML when available
            if part.get("mimeType") == "text/html":
                return content

    return ""


def get_header(headers, name):
    for header in headers:
        if header["name"].lower() == name.lower():
            return header["value"]

    return None


def extract_name_from_sender(sender):
    """
    Example:
    Abhijeet Phadnis via LinkedIn <invitations@linkedin.com>

    -> Abhijeet Phadnis
    """

    if not sender:
        return None

    name = sender.split("<")[0].strip()

    name = re.sub(
        r"\s+via LinkedIn\s*$",
        "",
        name,
        flags=re.IGNORECASE
    )

    name = name.strip('"').strip()

    return name


def parse_linkedin_email(html):
    soup = BeautifulSoup(html, "html.parser")

    text = soup.get_text(
        "\n",
        strip=True
    )

    links = []

    for tag in soup.find_all("a", href=True):
        href = tag["href"]

        if "linkedin.com" in href:
            links.append(href)

    return text, links


def main():

    service = get_gmail_service()

    labels = service.users().labels().list(
        userId="me"
    ).execute().get("labels", [])

    label_id = None

    for label in labels:
        if label["name"] == LABEL_NAME:
            label_id = label["id"]
            break

    if not label_id:
        raise RuntimeError(
            f"{LABEL_NAME} label not found"
        )

    result = service.users().messages().list(
        userId="me",
        labelIds=[label_id],
        maxResults=20
    ).execute()

    messages = result.get("messages", [])

    print(
        f"Found {len(messages)} acceptance emails"
    )

    for item in messages:

        msg = service.users().messages().get(
            userId="me",
            id=item["id"],
            format="full"
        ).execute()

        payload = msg["payload"]

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

        name = extract_name_from_sender(
            sender
        )

        body = extract_body(
            payload
        )

        text, links = parse_linkedin_email(
            body
        )

        print("\n" + "=" * 70)

        print("Gmail ID:")
        print(item["id"])

        print("\nName:")
        print(name)

        print("\nSubject:")
        print(subject)

        print("\nBody preview:")
        print(text[:1000])

        print("\nLinkedIn links:")

        for link in links[:10]:
            print(link)


if __name__ == "__main__":
    main()