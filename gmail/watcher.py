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
from gmail.classifier import classify_email
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
    'OR subject:application OR subject:recruiter OR subject:offer OR subject:opportunity '
    'OR subject:naukri OR from:naukri OR "job alert" OR "recommended jobs" '
    'OR from:linkedin.com OR from:indeed.com OR from:instahyre.com OR from:cutshort.io '
    'OR from:googlealerts-noreply@google.com '
    'OR subject:"jobs for you" OR subject:"new jobs" OR subject:"Google Alert"'
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


def _score_and_card(
    jobs: list[Any], store: SqliteStore, bot: TelegramBot, *, naukri_style: bool
) -> int:
    """Score parsed alert jobs, persist the unseen ones, send a card for each
    non-weak one. Returns the number carded."""
    from orchestrator.models import Candidate
    from orchestrator.policies import load_evidence, load_preferences
    from orchestrator.scorer import score_job
    from telegram.cards import inline_buttons, candidate_card, naukri_buttons, naukri_card

    prefs = load_preferences()
    evidence = load_evidence()
    known = store.known_job_keys()
    candidates = [
        Candidate(job=job, score=score_job(job, prefs, evidence))
        for job in jobs
        if job.canonical_key not in known
    ]
    store.persist(candidates)
    carded = 0
    for candidate in candidates:
        if candidate.score.bucket == "weak":
            continue
        if bot.configured:
            if naukri_style:
                bot.send_message(naukri_card(candidate), naukri_buttons(candidate))
            else:
                bot.send_message(candidate_card(candidate), inline_buttons(candidate))
        carded += 1
    return carded


def _handle_naukri_alert(payload: dict[str, Any], store: SqliteStore, bot: TelegramBot) -> str:
    from sources.naukri import jobs_from_alert_email

    jobs = jobs_from_alert_email(extract_html(payload) or extract_text(payload))
    carded = _score_and_card(jobs, store, bot, naukri_style=True)
    return f"naukri_alert:{len(jobs)} parsed, {carded} carded"


def _handle_job_alert(
    provider: str, payload: dict[str, Any], subject: str, sender: str, store: SqliteStore, bot: TelegramBot
) -> str:
    from sources.job_alert_emails import jobs_from_alert

    _, jobs = jobs_from_alert(sender, subject, extract_html(payload), extract_text(payload))
    carded = _score_and_card(jobs, store, bot, naukri_style=False)
    return f"{provider}_alert:{len(jobs)} parsed, {carded} carded"


_ALWAYS_HUMAN = {"offer", "unknown"}


def classify_inbound(sender: str, subject: str, snippet: str, provider: Any) -> dict[str, Any]:
    """Deterministic base classification, optionally enriched by Claude.

    The deterministic safety gate always wins: offers / compensation / ambiguous
    mail stay ``needs_human`` regardless of what Claude returns, and Claude is
    never allowed to downgrade an ``offer`` to something auto-actionable.
    """
    base = classify_email(sender, subject, snippet)
    if os.getenv("CLAUDE_MODE", "mock") != "claude":
        return base
    try:
        enriched = provider.classify_reply({"sender": sender, "subject": subject, "snippet": snippet})
    except Exception as exc:  # noqa: BLE001 - fall back to deterministic
        base["claude_error"] = str(exc)
        return base
    merged = dict(base)
    merged["company"] = enriched.get("company") or base.get("company")
    merged["role"] = enriched.get("role") or base.get("role")
    if base["type"] == "offer" or base["type"] in _ALWAYS_HUMAN:
        merged["needs_human"] = True
    else:
        merged["type"] = enriched.get("type", base["type"])
        merged["recommended_action"] = enriched.get("recommended_action", base["recommended_action"])
        merged["needs_human"] = bool(base["needs_human"] or enriched.get("needs_human"))
    merged["provider"] = "claude+deterministic"
    return merged


def _handle_interview_invite(
    payload: dict[str, Any], subject: str, snippet: str, classification: dict[str, Any],
    store: SqliteStore, provider: Any, bot: TelegramBot,
) -> None:
    from interview.prep import build_prep_pack, write_prep_pack
    from interview.schedule import extract_interview_datetime, propose_calendar_event

    body = extract_text(payload) or extract_html(payload) or snippet
    company = classification.get("company") or "the company"
    role = classification.get("role") or "the role"
    when = extract_interview_datetime(f"{subject}\n{body}")

    pack = build_prep_pack({"company": company, "role": role, "description": body}, provider=provider)
    if when:
        pack["scheduled_for"] = when.isoformat()
    path = write_prep_pack(pack)
    proposal = propose_calendar_event(company, role, when, notes=f"From: {subject}")
    store.append_event("interview_prep_ready", None, {"artifact": str(path), "calendar_proposal": proposal})

    if bot.configured:
        parts = [
            f"🎯 INTERVIEW INVITE · {company}",
            f"Role: {role}",
            f"When: {when.isoformat() if when else 'not detected — confirm from the email'}",
            "",
            f"Prep pack: {path}",
            "",
            "Calendar event is NOT created. Reply/approve to have it added to Google Calendar.",
        ]
        bot.send_message("\n".join(parts))


def _email_alerts_config() -> dict[str, Any]:
    from orchestrator.pipeline import load_sources_config

    cfg = load_sources_config()
    return cfg.get("sources", {}).get("email_alerts", {})


def _alert_source_enabled(provider: str) -> bool:
    """Per-platform on/off switch (config/sources.yaml: sources.email_alerts.<name>.enabled).
    Defaults to on - these are free, zero-cost parsers of mail the user already
    subscribed to, so there is no reason to default any of them off."""
    try:
        entry = _email_alerts_config().get(provider, {})
    except Exception:  # noqa: BLE001 - config problems must never block Gmail processing
        return True
    return bool(entry.get("enabled", True))


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

    if ("naukri" in sender.lower() or "naukri" in subject.lower()) and _alert_source_enabled("naukri"):
        result = _handle_naukri_alert(payload, store, bot)
        store.mark_email_processed(message_id, "naukri_alert")
        return result

    from sources.job_alert_emails import alert_provider

    alert_name = alert_provider(sender, subject)
    if alert_name and _alert_source_enabled(alert_name):
        result = _handle_job_alert(alert_name, payload, subject, sender, store, bot)
        store.mark_email_processed(message_id, f"{alert_name}_alert")
        return result

    classification = classify_inbound(sender, subject, snippet, provider)
    store.append_event(
        "email_classified",
        None,
        {"message_id": message_id, "subject": subject, **classification},
    )
    store.mark_email_processed(message_id, f"reply:{classification.get('type')}")

    if classification.get("type") == "interview_invite":
        _handle_interview_invite(payload, subject, snippet, classification, store, provider, bot)
    if bot.configured:
        prefix = "🚨 ESCALATE" if classification.get("needs_human") else "📨 Inbox"
        bot.send_message(
            f"{prefix} · {classification.get('type')}\n\n"
            f"From: {sender}\nSubject: {subject}\n\n"
            f"Action: {classification.get('recommended_action')}\n{snippet[:400]}"
        )
    return f"reply:{classification.get('type')}"


def run_once(provider: Any | None = None) -> dict[str, Any]:
    load_dotenv()
    if not credentials_present():
        return {"status": "disabled", "reason": "Gmail secrets/credentials.json + token.json missing."}
    query = os.getenv("GMAIL_QUERY", DEFAULT_QUERY)
    max_results = int(os.getenv("GMAIL_MAX_RESULTS", "25"))
    store = SqliteStore(ROOT / "state")
    if provider is None:
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
