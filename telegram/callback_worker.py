"""Telegram callback worker - the approval layer.

Long-polls ``getUpdates`` and dispatches inline-button callbacks against the
SQLite store. Approvals are idempotent (status is checked before mutation, and
Telegram's own ``offset`` prevents re-delivery). No message is ever sent on
behalf of the user - approving a LinkedIn draft only marks it approved and
re-shows the text with an OPEN LINKEDIN link for manual sending.
"""

from __future__ import annotations

import os
import time
from typing import Any

from dotenv import load_dotenv

from application.factory import NotP0Error, prepare_application
from application.artifacts import create_artifact_directory
from intelligence.provider import get_intelligence_provider
from orchestrator.pipeline import ROOT
from orchestrator.policies import load_evidence
from state.store import SqliteStore
from telegram.bot import TelegramBot
from telegram.cards import (
    connection_card,
    draft_buttons,
    people_search_buttons,
    people_search_card,
    url_button,
    why_score_card,
)


def _split(data: str) -> tuple[str, str]:
    parts = data.split(":", 1)
    return (parts[0], parts[1] if len(parts) > 1 else "")


def _artifact_dir(candidate: Any) -> Any:
    return create_artifact_directory(candidate.job, ROOT / "artifacts" / "generated")


def _ensure_application(candidate: Any, store: SqliteStore, provider: Any) -> Any:
    path = _artifact_dir(candidate)
    expected = ["fit_report.md", "evidence_matrix.md", "recruiter_email.txt", "referral_message.txt", "application_notes.md"]
    if all((path / name).exists() for name in expected):
        return path
    return prepare_application(
        candidate,
        load_evidence(),
        store,
        provider,
        ROOT / "artifacts" / "generated",
        force=True,
    )


_KIND_LABEL = {
    "prepare": "full application package",
    "resume": "tailored resume",
    "email": "recruiter email",
    "linkedin": "LinkedIn / referral note",
}
_TAILORED_MARKER = "_claude_tailored.json"


def _has_real_draft(candidate: Any) -> bool:
    """True once a Claude drafting run has delivered real artifacts for this job.

    Until then a non-live provider only has placeholder text to offer, so the
    button press is queued instead.
    """
    return (_artifact_dir(candidate) / _TAILORED_MARKER).exists()


def _read_artifact(path: Any, name: str, limit: int = 3200) -> str:
    target = path / name
    if not target.exists():
        return f"NEEDS_CONFIRMATION: {name} was not generated."
    text = target.read_text(encoding="utf-8").strip()
    return text[:limit] + ("\n\n...[truncated]" if len(text) > limit else "")


def handle_callback(
    data: str,
    callback_id: str,
    bot: TelegramBot,
    store: SqliteStore,
    provider: Any,
) -> str:
    """Handle one callback. Returns a short status string (also used in tests)."""
    action, arg = _split(data)

    if action == "conn" and arg:
        sub, cid_raw = _split(arg)
        if not cid_raw.isdigit():
            return "ignored:bad_connection_id"
        cid = int(cid_raw)
        connection = store.get_connection(cid)
        if connection is None:
            bot.answer_callback_query(callback_id, "Connection not found.")
            return "not_found"
        if connection["status"] in {"approved", "skipped"}:
            bot.answer_callback_query(callback_id, f"Already {connection['status']}.")
            return f"noop:{connection['status']}"
        if sub == "approve":
            store.set_connection_status(cid, "approved")
            store.append_event("connection_approved", connection.get("matched_job_key"), {"connection_id": cid})
            bot.answer_callback_query(callback_id, "Approved - send manually.")
            buttons = [[url_button("👤 OPEN LINKEDIN", connection["linkedin_url"])]] if connection.get("linkedin_url") else None
            bot.send_message(
                "APPROVED (send manually)\n\n"
                f"{connection['name']}\n\n{connection.get('generated_message') or ''}",
                {"inline_keyboard": buttons} if buttons else None,
            )
            return "approved"
        if sub == "skip":
            store.set_connection_status(cid, "skipped")
            bot.answer_callback_query(callback_id, "Skipped.")
            return "skipped"
        return "ignored:unknown_conn_action"

    # job actions - arg is a job_key which itself contains a colon
    if action in {"prepare", "skip", "why", "jd", "people", "resume", "email", "linkedin"} and arg:
        job_key = arg
        latest = store.load_latest_jobs()
        candidate = latest.get(job_key)
        if candidate is None:
            bot.answer_callback_query(callback_id, "Job not found in state.")
            return "not_found"

        if action == "skip":
            store.set_job_status(job_key, "skipped")
            store.append_event("job_skipped", job_key, {})
            bot.answer_callback_query(callback_id, "Skipped.")
            return "skipped"
        if action == "why":
            bot.answer_callback_query(callback_id)
            bot.send_message(why_score_card(candidate))
            return "explained"
        if action == "jd":
            bot.answer_callback_query(callback_id)
            jd = candidate.job.description or "(no description stored)"
            bot.send_message(f"📋 {candidate.job.company} · {candidate.job.title}\n\n{jd[:3500]}")
            return "jd_sent"
        if action == "people":
            bot.answer_callback_query(callback_id)
            contacts = store.contacts_for_company(candidate.job.company)
            bot.send_message(people_search_card(candidate, contacts), people_search_buttons(candidate))
            return "people_sent"
        if action in {"prepare", "resume", "email", "linkedin"}:
            # A non-live provider (CLAUDE_MODE=mock, i.e. the whole GitHub Actions
            # setup) can only produce placeholder text. Queue the request so a
            # Claude Code drafting run writes the real artifacts, then delivers
            # them here. Once that has happened (_TAILORED_MARKER present) the
            # button serves the real draft immediately.
            if not getattr(provider, "is_live", False) and not _has_real_draft(candidate):
                req_id = store.enqueue_draft_request(job_key, action)
                store.append_event("draft_requested", job_key, {"kind": action, "request_id": req_id})
                bot.answer_callback_query(callback_id, "Queued for Claude ✍️")
                bot.send_message(
                    f"✍️ QUEUED FOR CLAUDE — {_KIND_LABEL[action]}\n\n"
                    f"{candidate.job.company} · {candidate.job.title}\n\n"
                    f"Request #{req_id} is in the queue. The next Claude drafting run delivers the "
                    f"real, evidence-grounded {_KIND_LABEL[action]} here — not a placeholder. "
                    f"Nothing is ever submitted or sent for you."
                )
                return f"queued:{action}"
            bot.answer_callback_query(callback_id, "Preparing draft...")
            return deliver_draft(action, candidate, store, provider, bot)

    return "ignored"


def deliver_draft(
    action: str,
    candidate: Any,
    store: SqliteStore,
    provider: Any,
    bot: TelegramBot,
) -> str:
    """Build the artifact package if needed and push the requested draft to
    Telegram. Shared by the live-provider button path and the queue drain
    (``run_agent.py drafts --deliver``)."""
    try:
        path = _ensure_application(candidate, store, provider)
    except NotP0Error as exc:
        bot.send_message(f"❌ Not preparing: {exc}")
        return "prepare_refused"

    if action == "prepare":
        store.set_job_status(candidate.job_key, "preparing")
        store.append_event("application_prepared", candidate.job_key, {"artifact_dir": str(path)})
        bot.send_message(
            f"📦 Application prepared for {candidate.job.company}\n\nArtifacts: {path}",
            people_search_buttons(candidate),
        )
        return "prepared"
    if action == "resume":
        resume = _read_artifact(path, "resume.md")
        send_document = getattr(bot, "send_document", None)
        if callable(send_document) and (path / "resume.md").exists():
            send_document(
                path / "resume.md",
                caption=f"Updated resume draft for {candidate.job.company} - {candidate.job.title}",
            )
        bot.send_message(
            f"📄 UPDATED RESUME DRAFT\n\n{candidate.job.company} · {candidate.job.title}\n\n{resume}\n\nArtifacts: {path}"
        )
        return "resume_sent"
    if action == "email":
        draft = _read_artifact(path, "recruiter_email.txt")
        bot.send_message(
            f"✉️ RECRUITER EMAIL DRAFT\n\n{candidate.job.company} · {candidate.job.title}\n\n{draft}",
            draft_buttons(candidate, kind="email", draft=draft),
        )
        return "email_draft_sent"
    draft = _read_artifact(path, "linkedin_message.txt")
    if draft.startswith("NEEDS_CONFIRMATION"):
        draft = _read_artifact(path, "referral_message.txt")
    bot.send_message(
        f"💬 LINKEDIN / REFERRAL DRAFT\n\n{candidate.job.company} · {candidate.job.title}\n\n{draft}\n\nSend manually only.",
        draft_buttons(candidate, kind="linkedin", draft=draft),
    )
    return "linkedin_draft_sent"


_OFFSET_KEY = "telegram_callback_offset"


def drain_callbacks(
    bot: TelegramBot,
    store: SqliteStore,
    provider: Any,
    max_updates: int = 100,
) -> dict[str, Any]:
    """Process every pending callback once, then return - no long-polling.

    This is what a scheduled / cloud run uses instead of the always-on loop:
    approvals are handled on the next scheduled tick. The Telegram ``offset`` is
    persisted in SQLite so nothing is processed twice across runs.
    """
    if not bot.configured:
        return {"status": "skipped", "reason": "telegram not configured", "processed": 0}
    stored = store.get_runtime(_OFFSET_KEY)
    offset = int(stored) if stored and stored.lstrip("-").isdigit() else None
    processed: list[str] = []
    try:
        updates = bot.get_updates(offset, timeout=0).get("result", [])
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error": str(exc), "processed": 0}
    for update in updates[:max_updates]:
        new_offset = update["update_id"] + 1
        callback = update.get("callback_query")
        if callback:
            try:
                processed.append(handle_callback(callback.get("data", ""), callback["id"], bot, store, provider))
            except Exception as exc:  # noqa: BLE001 - never let one callback break the drain
                processed.append(f"error:{type(exc).__name__}")
        store.set_runtime(_OFFSET_KEY, str(new_offset))
    return {"status": "ok", "processed": len(processed), "results": processed}


def main() -> None:
    load_dotenv()
    bot = TelegramBot()
    store = SqliteStore(ROOT / "state")
    provider = get_intelligence_provider(os.getenv("CLAUDE_MODE", "mock"))
    if not bot.configured:
        print("Telegram not configured (.env). Callback worker exiting.", flush=True)
        return

    print("Telegram callback worker started. Ctrl+C to stop.", flush=True)
    offset: int | None = None
    while True:
        try:
            updates = bot.get_updates(offset)
            for update in updates.get("result", []):
                offset = update["update_id"] + 1
                callback = update.get("callback_query")
                if not callback:
                    continue
                data = callback.get("data", "")
                print(f"callback: {data}", flush=True)
                try:
                    result = handle_callback(data, callback["id"], bot, store, provider)
                    print(f"  -> {result}", flush=True)
                except Exception as exc:  # noqa: BLE001 - keep the loop alive
                    print(f"  callback failed: {type(exc).__name__}: {exc}", flush=True)
        except KeyboardInterrupt:
            print("\nTelegram callback worker stopped.", flush=True)
            break
        except Exception as exc:  # noqa: BLE001
            print(f"polling failed: {type(exc).__name__}: {exc}; retrying in 15s", flush=True)
            time.sleep(15)


if __name__ == "__main__":
    main()
