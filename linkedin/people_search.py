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

from typing import Any, Callable

_ROLE_HINTS = (
    "recruiter", "talent acquisition", "engineering manager",
    "hiring manager", "HR", "people operations",
)

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


def search_people(
    company: str,
    role_hint: str | None = None,
    max_results: int = 5,
    *,
    search_fn: SearchFn | None = None,
) -> list[dict[str, str]]:
    """Publicly-indexed LinkedIn profile hits for ``company``, most relevant
    first. Never raises - a failed/blocked search just yields no results,
    since the manual search-link button is always shown alongside this."""
    if not company:
        return []
    search = search_fn or _default_search
    query = _build_query(company, role_hint)
    try:
        hits = search(query, max_results=max_results * 3)
    except Exception:  # noqa: BLE001 - web search must never break the card flow
        return []

    people: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    for hit in hits:
        person = _parse_hit(hit)
        if person is None or person["url"] in seen_urls:
            continue
        seen_urls.add(person["url"])
        people.append(person)
        if len(people) >= max_results:
            break
    return people
