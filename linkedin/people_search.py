"""Find real, publicly-indexed LinkedIn profiles for a company via a normal
web search engine (DuckDuckGo) - never by logging into or scraping LinkedIn
itself. That distinction matters: CLAUDE.md forbids LinkedIn scraping/browser
automation because LinkedIn actively detects and bans accounts for it; a
public search engine query carries no such risk to the user's account.

Ported approach from the linkedin-ai-assistant predecessor
(app/services/web_search_service.py on the `main` branch), which used the
same ddgs-based technique to research companies/people.

Results are unverified web-search hits, not confirmed contacts - the caller
must present them as "search results to verify yourself", never as a
guaranteed-accurate directory.
"""

from __future__ import annotations

import re
from typing import Any, Callable
from urllib.parse import urlparse

_ROLE_HINTS = (
    "recruiter", "talent acquisition", "engineering manager",
    "hiring manager", "HR", "people operations",
)

# Hosts that turn up for "<company> official website" but are never the
# company's own domain - never guess an email @ one of these.
_NOT_COMPANY_DOMAINS = {
    "linkedin.com", "glassdoor.com", "indeed.com", "crunchbase.com",
    "wikipedia.org", "facebook.com", "twitter.com", "x.com", "instagram.com",
    "youtube.com", "github.com", "medium.com", "ambitionbox.com",
    "google.com", "bing.com",
}

SearchFn = Callable[..., list[dict[str, Any]]]


def _default_search(query: str, *, max_results: int) -> list[dict[str, Any]]:
    from ddgs import DDGS

    return DDGS(timeout=8).text(
        query, region="in-en", safesearch="moderate", max_results=max_results
    )


def _build_query(company: str, role_hint: str | None) -> str:
    role_terms = " OR ".join(f'"{term}"' for term in _ROLE_HINTS)
    parts = [f'"{company}"', f"({role_terms})", "linkedin"]
    if role_hint:
        parts.insert(1, f'"{role_hint}"')
    return " ".join(parts)


def _parse_hit(hit: dict[str, Any]) -> dict[str, str] | None:
    url = hit.get("href") or ""
    if "linkedin.com/in/" not in url:
        return None  # a job posting / company page / post, not a person profile
    title = (hit.get("title") or "").strip()
    name, _, role = title.partition(" - ")
    return {"name": name.strip() or title, "title": role.strip(), "url": url}


def _domain_of(url: str) -> str | None:
    host = (urlparse(url).netloc or "").lower()
    return host[4:] if host.startswith("www.") else host or None


def guess_company_domain(company: str, *, search_fn: SearchFn | None = None) -> str | None:
    """Best-effort company domain from a public web search - never LinkedIn
    itself. Used only to build unverified email-pattern guesses; never treat
    this as confirmed."""
    if not company:
        return None
    search = search_fn or _default_search
    try:
        hits = search(f'"{company}" official website', max_results=5)
    except Exception:  # noqa: BLE001
        return None
    for hit in hits:
        domain = _domain_of(hit.get("href") or "")
        if domain and "." in domain and not any(
            domain == blocked or domain.endswith(f".{blocked}") for blocked in _NOT_COMPANY_DOMAINS
        ):
            return domain
    return None


def guess_emails(name: str, domain: str | None) -> list[str]:
    """Common corporate email-pattern guesses for ``name`` @ ``domain``.
    These are PATTERN GUESSES, not looked-up addresses - there is no email-
    finder API in this project (CLAUDE.md: no paid API keys). Always present
    them as unverified; confirm before sending anything to one."""
    if not domain:
        return []
    parts = [p for p in re.split(r"[^A-Za-z]+", name.lower()) if p]
    if len(parts) < 2:
        return []
    first, last = parts[0], parts[-1]
    candidates = [
        f"{first}.{last}@{domain}",
        f"{first}{last}@{domain}",
        f"{first[0]}{last}@{domain}",
        f"{first}@{domain}",
    ]
    seen: set[str] = set()
    out: list[str] = []
    for email in candidates:
        if email not in seen:
            seen.add(email)
            out.append(email)
    return out


def search_people(
    company: str,
    role_hint: str | None = None,
    max_results: int = 5,
    *,
    search_fn: SearchFn | None = None,
    guess_email: bool = True,
) -> list[dict[str, Any]]:
    """Publicly-indexed LinkedIn profile hits for ``company``, most relevant
    first, each optionally carrying unverified email-pattern guesses. Never
    raises - a failed/blocked search just yields no results, since the
    manual search-link button is always shown alongside this."""
    if not company:
        return []
    search = search_fn or _default_search
    query = _build_query(company, role_hint)
    try:
        hits = search(query, max_results=max_results * 3)
    except Exception:  # noqa: BLE001 - web search must never break the card flow
        return []

    people: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for hit in hits:
        person = _parse_hit(hit)
        if person is None or person["url"] in seen_urls:
            continue
        seen_urls.add(person["url"])
        people.append(person)
        if len(people) >= max_results:
            break

    if guess_email and people:
        domain = guess_company_domain(company, search_fn=search_fn)
        for person in people:
            person["guessed_emails"] = guess_emails(person["name"], domain)
    return people
