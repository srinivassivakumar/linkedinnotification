"""Gmail OAuth credential loader.

File-based OAuth, ported from the linkedin-ai-assistant project. Put
``credentials.json`` (OAuth client) and ``token.json`` (authorized user token)
in ``ClaudeJob/secrets/`` - both are gitignored. The token was already authorized
for the read-only Gmail scope, so no browser flow runs unless it is missing or
revoked.
"""

from __future__ import annotations

from pathlib import Path

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

ROOT = Path(__file__).resolve().parents[1]
CREDENTIALS_FILE = ROOT / "secrets" / "credentials.json"
TOKEN_FILE = ROOT / "secrets" / "token.json"


def credentials_present() -> bool:
    return CREDENTIALS_FILE.exists() and TOKEN_FILE.exists()


def get_credentials():
    """Return valid Google credentials, refreshing or running the flow as needed."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")

    return creds


def get_gmail_service():
    """Return an authenticated Gmail API client."""
    from googleapiclient.discovery import build

    return build("gmail", "v1", credentials=get_credentials(), cache_discovery=False)


if __name__ == "__main__":
    # `python -m gmail.auth` - run the browser OAuth flow and (re)write
    # secrets/token.json. Use this whenever the cloud tick logs
    # "invalid_grant: Token has been expired or revoked" for Gmail.
    creds = get_credentials()
    print(f"token written to {TOKEN_FILE} (valid={creds.valid})")
    print("Now update the GitHub secret:")
    print("  gh secret set GMAIL_TOKEN_JSON --repo srinivassivakumar/linkedinnotification < secrets/token.json")
