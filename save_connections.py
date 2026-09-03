import os
import base64

from dotenv import load_dotenv

from app.db import get_connection
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


def message_already_processed(
    gmail_message_id
):

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


def mark_processed(
    gmail_message_id
):

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
            f"Gmail label "
            f"'{LABEL_NAME}' not found"
        )


    result = service.users().messages().list(
        userId="me",
        labelIds=[
            label_id
        ],
        maxResults=50
    ).execute()


    messages = result.get(
        "messages",
        []
    )


    print(
        f"Found {len(messages)} "
        f"labeled emails"
    )


    new_count = 0
    skipped_count = 0
    failed_count = 0


    for item in messages:

        gmail_message_id = item["id"]


        # -------------------------------------
        # DUPLICATE CHECK
        # -------------------------------------

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

            # ---------------------------------
            # DOWNLOAD EMAIL
            # ---------------------------------

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


            # ---------------------------------
            # GET LINKEDIN SENDER NAME
            # ---------------------------------

            sender = get_header(
                headers,
                "From"
            )

            sender_name = (
                sender_name_from_header(
                    sender
                )
            )


            # ---------------------------------
            # EXTRACT EMAIL HTML
            # ---------------------------------

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


            # ---------------------------------
            # PARSE LINKEDIN EMAIL
            # ---------------------------------

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


            # ---------------------------------
            # VALIDATE MINIMUM DATA
            # ---------------------------------

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


            # ---------------------------------
            # BUILD PERSON OBJECT
            # ---------------------------------

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


            # ---------------------------------
            # SAVE BASIC CONNECTION
            # ---------------------------------

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


            # ---------------------------------
            # AI + WEB RESEARCH + TELEGRAM
            # ---------------------------------

            processing_result = (
                process_and_send_for_approval(
                    connection_id,
                    person
                )
            )


            # ---------------------------------
            # ONLY MARK EMAIL PROCESSED
            # AFTER PIPELINE FINISHES
            # ---------------------------------

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