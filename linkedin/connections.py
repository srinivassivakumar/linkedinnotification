"""Cross-link an accepted LinkedIn connection with our open jobs.

Flow (build guide section 16):
  accepted connection -> infer company / person type -> query OUR jobs table for
  that company -> Claude drafts a referral message (match) or a networking-only
  message (no match) -> store connection as a human-path signal -> Telegram
  approval card.

No web search, no scraping, no automated messaging. The draft is sent manually.
"""

from __future__ import annotations

import re
from typing import Any

from state.store import SqliteStore

_COMPANY_RE = re.compile(r"(?:@|\bat)\s+([A-Za-z0-9][\w&.\- ]{1,40})", re.IGNORECASE)


def guess_company(headline: str | None) -> str | None:
    if not headline:
        return None
    match = _COMPANY_RE.search(headline)
    if not match:
        return None
    company = match.group(1).strip(" .-")
    # stop at obvious separators
    for sep in ("|", "•", " - ", ","):
        if sep in company:
            company = company.split(sep)[0].strip()
    return company or None


def process_accepted_connection(
    parsed: dict[str, Any],
    store: SqliteStore,
    provider: Any,
    gmail_message_id: str | None = None,
) -> dict[str, Any]:
    """Persist and evaluate one accepted connection. Returns the stored row."""
    if gmail_message_id:
        existing = store.connection_by_gmail_id(gmail_message_id)
        if existing is not None:
            return existing

    person = {
        "name": parsed.get("name"),
        "current_title": parsed.get("headline"),
        "linkedin_url": parsed.get("linkedin_profile_url"),
    }
    connection_id = store.save_connection(person, gmail_message_id=gmail_message_id)

    company_guess = guess_company(parsed.get("headline"))
    company_jobs = store.open_jobs_for_company(company_guess) if company_guess else []

    research = provider.research_connection(
        {
            "name": parsed.get("name"),
            "headline": parsed.get("headline"),
            "location": parsed.get("location"),
            "company": company_guess,
        },
        company_jobs,
    )
    store.update_connection_result(connection_id, research)
    store.append_event(
        "connection_discovered",
        research.get("matched_job_key"),
        {"connection_id": connection_id, "person_type": research.get("person_type")},
    )
    return store.get_connection(connection_id) or {}
