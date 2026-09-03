from pathlib import Path

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build


SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly"
]

BASE = Path(__file__).resolve().parents[2]

CREDS = BASE / "secrets" / "credentials.json"
TOKEN = BASE / "secrets" / "token.json"


def get_gmail_service():
    creds = None

    if TOKEN.exists():
        creds = Credentials.from_authorized_user_file(
            str(TOKEN),
            SCOPES
        )

    if not creds or not creds.valid:

        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())

        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDS),
                SCOPES
            )

            creds = flow.run_local_server(port=0)

        TOKEN.write_text(
            creds.to_json(),
            encoding="utf-8"
        )

    return build(
        "gmail",
        "v1",
        credentials=creds
    )