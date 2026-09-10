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

from application.factory import prepare_application
from intelligence.provider import get_intelligence_provider
from orchestrator.pipeline import ROOT
from orchestrator.policies import load_evidence
from state.store import SqliteStore
from telegram.bot import TelegramBot
from telegram.cards import connection_card, url_button, why_score_card


def _split(data: str) -> tuple[str, str]:
    parts = data.split(":", 1)
    return (parts[0], parts[1] if len(parts) > 1 else "")


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
    if action in {"prepare", "skip", "why", "jd", "people"} and arg:
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
            if contacts:
                lines = [f"👥 {candidate.job.company}", ""]
                for c in contacts[:5]:
                    lines.append(f"- {c.get('name')} ({c.get('title') or c.get('role_type')}) {c.get('public_profile_url') or ''}")
                bot.send_message("\n".join(lines))
            else:
                hint = (candidate.intelligence or {}).get("human_path_hint") or "No stored contact yet."
                bot.send_message(f"👥 {candidate.job.company}\n\nNo saved contact. Hint: {hint}")
            return "people_sent"
        if action == "prepare":
            store.set_job_status(job_key, "preparing")
            bot.answer_callback_query(callback_id, "Preparing application...")
            path = prepare_application(
                candidate, load_evidence(), store, provider, ROOT / "artifacts" / "generated"
            )
            store.append_event("application_prepared", job_key, {"artifact_dir": str(path)})
            bot.send_message(f"📦 Application prepared for {candidate.job.company}\n\nArtifacts: {path}")
            return "prepared"

    return "ignored"


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
