"""Background Gmail watcher - closes the loop.

Polls Gmail (read-only scope), routes each unseen message:
  * LinkedIn "accepted your invitation"  -> connection cross-link + Telegram card
  * everything else (recruiter/ATS/alert) -> Claude reply classifier + event + Telegram

Idempotent via the ``processed_emails`` table. Sends nothing on the user's
behalf; offers/compensation/ambiguous messages are escalated, never auto-handled.
"""

from __future__ import annotations

import base64
import os
import time
from typing import Any

from dotenv import load_dotenv

from gmail.auth import credentials_present, get_gmail_service
from intelligence.provider import get_intelligence_provider
from linkedin.connections import process_accepted_connection
from linkedin.email_parser import parse_acceptance_email
from orchestrator.pipeline import ROOT
from state.store import SqliteStore
from telegram.bot import TelegramBot
from telegram.cards import connection_buttons, connection_card

DEFAULT_QUERY = (
    'newer_than:3d ('
    'subject:"accepted your invitation" OR subject:interview OR subject:assessment '
    'OR subject:application OR subject:recruiter OR subject:offer OR subject:opportunity'
    ')'
)


def decode_base64url(data: str | None) -> str:
    if not data:
        return ""
    data += "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data.encode("utf-8")).decode("utf-8", errors="ignore")


def extract_html(payload: dict[str, Any]) -> str:
    if payload.get("mimeType") == "text/html":
        data = payload.get("body", {}).get("data")
        if data:
            return decode_base64url(data)
    for part in payload.get("parts", []):
        result = extract_html(part)
        if result:
            return result
    return ""


def extract_text(payload: dict[str, Any]) -> str:
    if payload.get("mimeType") == "text/plain":
        return decode_base64url(payload.get("body", {}).get("data"))
    for part in payload.get("parts", []):
        result = extract_text(part)
        if result:
            return result
    return ""


def header(headers: list[dict[str, str]], name: str) -> str | None:
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value")
    return None


def sender_name(value: str | None) -> str | None:
    return value.split("<")[0].strip() if value else None


def list_messages(service: Any, query: str, max_results: int) -> list[dict[str, Any]]:
    resp = service.users().messages().list(userId="me", q=query, maxResults=min(max_results, 100)).execute()
    return resp.get("messages", [])[:max_results]


def _handle_naukri_alert(payload: dict[str, Any], store: SqliteStore, bot: TelegramBot) -> str:
    from orchestrator.models import Candidate
    from orchestrator.policies import load_evidence, load_preferences
    from orchestrator.scorer import score_job
    from sources.naukri import jobs_from_alert_email
    from telegram.cards import candidate_card, inline_buttons

    prefs = load_preferences()
    evidence = load_evidence()
    jobs = jobs_from_alert_email(extract_html(payload))
    candidates = [Candidate(job=job, score=score_job(job, prefs, evidence)) for job in jobs]
    new = store.diff_new_or_changed(candidates)
    store.persist(new)
    carded = 0
    for candidate in new:
        if candidate.score.bucket == "weak":
            continue
        if bot.configured:
            bot.send_message(candidate_card(candidate), inline_buttons(candidate))
        carded += 1
    return f"naukri:{len(jobs)} parsed, {carded} carded (manual OPEN/APPLY only)"


def _is_linkedin_acceptance(subject: str, sender: str) -> bool:
    return "accepted your invitation" in subject.lower() or (
        "linkedin" in (sender or "").lower() and "invitation" in subject.lower()
    )


def process_message(
    service: Any, message_id: str, store: SqliteStore, provider: Any, bot: TelegramBot
) -> str:
    if store.email_processed(message_id):
        return "skipped:already_processed"

    msg = service.users().messages().get(userId="me", id=message_id, format="full").execute()
    payload = msg.get("payload", {})
    headers = payload.get("headers", [])
    subject = header(headers, "Subject") or ""
    sender = header(headers, "From") or ""
    snippet = msg.get("snippet", "")

    if _is_linkedin_acceptance(subject, sender):
        html = extract_html(payload)
        parsed = parse_acceptance_email(html, sender_name(sender))
        if not parsed.get("name") or not parsed.get("linkedin_profile_url"):
            store.mark_email_processed(message_id, "linkedin_unparsed")
            return "linkedin:unparsed"
        connection = process_accepted_connection(parsed, store, provider, gmail_message_id=message_id)
        store.mark_email_processed(message_id, "linkedin_acceptance")
        if bot.configured and connection.get("status") == "awaiting_approval":
            bot.send_message(connection_card(connection), connection_buttons(connection))
        return "linkedin:carded"

    if "naukri" in sender.lower():
        result = _handle_naukri_alert(payload, store, bot)
        store.mark_email_processed(message_id, "naukri_alert")
        return result

    classification = provider.classify_reply(
        {"sender": sender, "subject": subject, "snippet": snippet}
    )
    store.append_event(
        "email_classified",
        None,
        {"message_id": message_id, "subject": subject, **classification},
    )
    store.mark_email_processed(message_id, f"reply:{classification.get('type')}")
    if bot.configured:
        prefix = "🚨 ESCALATE" if classification.get("needs_human") else "📨 Inbox"
        bot.send_message(
            f"{prefix} · {classification.get('type')}\n\n"
            f"From: {sender}\nSubject: {subject}\n\n"
            f"Action: {classification.get('recommended_action')}\n{snippet[:400]}"
        )
    return f"reply:{classification.get('type')}"


def run_once() -> dict[str, Any]:
    load_dotenv()
    if not credentials_present():
        return {"status": "disabled", "reason": "Gmail secrets/credentials.json + token.json missing."}
    query = os.getenv("GMAIL_QUERY", DEFAULT_QUERY)
    max_results = int(os.getenv("GMAIL_MAX_RESULTS", "25"))
    store = SqliteStore(ROOT / "state")
    provider = get_intelligence_provider(os.getenv("CLAUDE_MODE", "mock"))
    bot = TelegramBot()
    service = get_gmail_service()

    results: list[str] = []
    for item in list_messages(service, query, max_results):
        try:
            results.append(process_message(service, item["id"], store, provider, bot))
        except Exception as exc:  # noqa: BLE001 - report and continue
            print(f"message {item['id']} failed: {type(exc).__name__}: {exc}", flush=True)
            results.append("error")
    return {"status": "ok", "processed": len(results), "results": results}


def run_watcher() -> dict[str, str]:
    """Back-compat entry point: single pass."""
    return run_once()


def main() -> None:
    poll = int(os.getenv("GMAIL_POLL_SECONDS", "60"))
    print(f"Gmail watcher started (every {poll}s). Ctrl+C to stop.", flush=True)
    while True:
        try:
            print(run_once(), flush=True)
        except KeyboardInterrupt:
            print("\nGmail watcher stopped.", flush=True)
            break
        except Exception as exc:  # noqa: BLE001
            print(f"watcher cycle failed: {type(exc).__name__}: {exc}", flush=True)
        time.sleep(poll)


if __name__ == "__main__":
    main()
