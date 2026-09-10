"""Hacker News "Ask HN: Who is hiring?" source - free, no key.

Each month a "Who is hiring?" thread is posted; every top-level comment is one
job ad in a loose ``Company | Role | Location | Remote | Salary | URL`` format.
This source finds the newest such thread via the free Algolia HN API, pulls its
comments, and turns the ones that mention enough relevant keywords into Job
objects. The deterministic scorer / filters do the rest.

    GET https://hn.algolia.com/api/v1/search_by_date?query=...&tags=story
    GET https://hn.algolia.com/api/v1/items/{story_id}
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

import requests

from orchestrator.models import Job

_SEARCH = "https://hn.algolia.com/api/v1/search_by_date"
_ITEM = "https://hn.algolia.com/api/v1/items"
_HEADERS = {"User-Agent": "Mozilla/5.0 career-agent"}
_URL_RE = re.compile(r"https?://[^\s<>\"')]+", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")


def _text(html: str) -> str:
    t = _TAG_RE.sub(" ", html or "")
    for a, b in (("&#x2F;", "/"), ("&#x27;", "'"), ("&amp;", "&"), ("&gt;", ">"), ("&lt;", "<"), ("&quot;", '"')):
        t = t.replace(a, b)
    return re.sub(r"\s+", " ", t).strip()


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


class HackerNewsWhoIsHiringSource:
    name = "hackernews"

    def __init__(self, config: dict[str, Any] | None = None, timeout_seconds: int = 20):
        self.config = config or {}
        self.enabled = bool(self.config.get("enabled", True))
        self.timeout_seconds = timeout_seconds
        self.keywords = [k.lower() for k in self.config.get("keywords", [
            "python", "machine learning", "ml", "ai", "llm", "rag", "data engineer",
            "mlops", "pytorch", "nlp", "genai", "data scientist",
        ])]
        self.min_keyword_hits = int(self.config.get("min_keyword_hits", 2))
        self.max_comments = int(self.config.get("max_comments", 400))
        self.errors: list[str] = []

    def fetch(self) -> list[Job]:
        self.errors = []
        if not self.enabled:
            return []
        try:
            story_id = self._latest_thread_id()
            if not story_id:
                self.errors.append("hackernews: no 'Who is hiring' thread found")
                return []
            comments = self._comments(story_id)
        except Exception as exc:  # noqa: BLE001
            self.errors.append(f"hackernews: {type(exc).__name__}: {exc}")
            print(f"hackernews: {type(exc).__name__}: {exc}", flush=True)
            return []

        jobs: list[Job] = []
        for c in comments[: self.max_comments]:
            job = self._map_comment(c)
            if job is not None:
                jobs.append(job)
        return jobs

    def _latest_thread_id(self) -> str | None:
        resp = requests.get(
            _SEARCH,
            params={"query": "Ask HN: Who is hiring?", "tags": "story", "hitsPerPage": 5},
            headers=_HEADERS,
            timeout=self.timeout_seconds,
        )
        resp.raise_for_status()
        for hit in resp.json().get("hits", []):
            if "who is hiring" in (hit.get("title") or "").lower():
                return hit.get("objectID")
        return None

    def _comments(self, story_id: str) -> list[dict[str, Any]]:
        resp = requests.get(f"{_ITEM}/{story_id}", headers=_HEADERS, timeout=self.timeout_seconds)
        resp.raise_for_status()
        return [c for c in (resp.json().get("children") or []) if c.get("text")]

    def _map_comment(self, comment: dict[str, Any]) -> Job | None:
        body = _text(comment.get("text", ""))
        low = body.lower()
        if sum(1 for k in self.keywords if k in low) < self.min_keyword_hits:
            return None

        head = body.split(". ")[0]
        parts = [p.strip() for p in re.split(r"\s*[|–—]\s*", head) if p.strip()]
        company = parts[0][:80] if parts else "(HN Who is hiring)"
        title = parts[1][:120] if len(parts) > 1 else "See post"
        loc_bits = [p for p in parts[2:6] if len(p) < 40]
        location = " / ".join(loc_bits) or ("Remote" if "remote" in low else None)

        urls = _URL_RE.findall(comment.get("text", ""))
        url = next((u for u in urls if "news.ycombinator.com" not in u), None)
        cid = comment.get("id")
        return Job(
            source=self.name,
            source_job_id=str(cid),
            company=company,
            title=title,
            location=location,
            description=body[:4000],
            url=url or f"https://news.ycombinator.com/item?id={cid}",
            # The "Who is hiring" thread is monthly and roles stay open all month,
            # so leave freshness unknown rather than let a day-of-month cutoff
            # hide the whole thread. The stable key still surfaces each once.
            posted_at=None,
            fetched_at=datetime.now(timezone.utc),
            raw={"hn_author": comment.get("author"), "commented_at": comment.get("created_at")},
        )
