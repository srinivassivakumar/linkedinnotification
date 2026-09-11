"""Free, keyless job-board JSON APIs - RemoteOK, Remotive, Arbeitnow.

All three publish a public JSON feed with no auth and no rate-limit key
required, so unlike Adzuna these need nothing in ``.env`` to work. Each feed
is global/remote-heavy, so a keyword gate (same idea as the Hacker News
source) keeps only postings relevant to this candidate's target roles.

    GET https://remoteok.com/api
    GET https://remotive.com/api/remote-jobs?search=<query>
    GET https://www.arbeitnow.com/api/job-board-api
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

import requests

from orchestrator.models import Job

_HEADERS = {"User-Agent": "Mozilla/5.0 career-agent"}
_TAG_RE = re.compile(r"<[^>]+>")

_DEFAULT_KEYWORDS = [
    "python", "machine learning", "ml engineer", "ai engineer", "llm", "rag",
    "data engineer", "mlops", "pytorch", "nlp", "genai", "data scientist",
]


def _strip_html(value: Any) -> str:
    text = _TAG_RE.sub(" ", str(value or ""))
    for a, b in (("&amp;", "&"), ("&gt;", ">"), ("&lt;", "<"), ("&quot;", '"'), ("&#39;", "'")):
        text = text.replace(a, b)
    return re.sub(r"\s+", " ", text).strip()


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _keyword_hits(blob: str, keywords: list[str]) -> int:
    low = blob.lower()
    return sum(1 for k in keywords if k in low)


class RemoteOKSource:
    """https://remoteok.com/api - the first element is a legal notice, not a job."""

    name = "remoteok"
    _URL = "https://remoteok.com/api"

    def __init__(self, config: dict[str, Any] | None = None, *, session: Any | None = None, timeout_seconds: int = 20):
        self.config = config or {}
        self.enabled = bool(self.config.get("enabled", False))
        self.keywords = [k.lower() for k in self.config.get("keywords", _DEFAULT_KEYWORDS)]
        self.min_keyword_hits = int(self.config.get("min_keyword_hits", 1))
        self.timeout_seconds = timeout_seconds
        self._session = session or requests
        self.errors: list[str] = []

    def fetch(self) -> list[Job]:
        self.errors = []
        if not self.enabled:
            return []
        try:
            resp = self._session.get(self._URL, headers=_HEADERS, timeout=self.timeout_seconds)
            resp.raise_for_status()
            items = resp.json()
        except Exception as exc:  # noqa: BLE001
            self.errors.append(f"remoteok: {type(exc).__name__}: {exc}")
            return []

        jobs: list[Job] = []
        for item in items:
            if not isinstance(item, dict) or not item.get("id") or "legal" in item:
                continue  # skip the legal-notice header row
            job = self._map(item)
            if job is not None:
                jobs.append(job)
        return jobs

    def _map(self, item: dict[str, Any]) -> Job | None:
        title = str(item.get("position") or item.get("title") or "").strip()
        company = str(item.get("company") or "").strip()
        if not title or not company:
            return None
        description = _strip_html(item.get("description"))
        tags = " ".join(str(t) for t in (item.get("tags") or []))
        blob = f"{title} {tags} {description}"
        if _keyword_hits(blob, self.keywords) < self.min_keyword_hits:
            return None
        job_id = str(item.get("id"))
        url = str(item.get("url") or f"https://remoteok.com/remote-jobs/{job_id}")
        return Job(
            source=self.name,
            source_job_id=job_id,
            company=company,
            title=title,
            location=str(item.get("location") or "Remote") or "Remote",
            description=description,
            url=url,
            posted_at=_parse_dt(item.get("date")),
            fetched_at=datetime.now(timezone.utc),
            employment_type="remote",
            raw={"tags": item.get("tags")},
        )


class RemotiveSource:
    """https://remotive.com/api/remote-jobs - optionally filtered server-side by ``search``."""

    name = "remotive"
    _URL = "https://remotive.com/api/remote-jobs"

    def __init__(self, config: dict[str, Any] | None = None, *, session: Any | None = None, timeout_seconds: int = 20):
        self.config = config or {}
        self.enabled = bool(self.config.get("enabled", False))
        self.queries = self.config.get("queries") or ["machine learning", "AI engineer", "data engineer"]
        self.keywords = [k.lower() for k in self.config.get("keywords", _DEFAULT_KEYWORDS)]
        self.min_keyword_hits = int(self.config.get("min_keyword_hits", 1))
        self.timeout_seconds = timeout_seconds
        self._session = session or requests
        self.errors: list[str] = []

    def fetch(self) -> list[Job]:
        self.errors = []
        if not self.enabled:
            return []
        jobs: list[Job] = []
        seen: set[str] = set()
        for query in self.queries:
            try:
                resp = self._session.get(self._URL, params={"search": query}, headers=_HEADERS, timeout=self.timeout_seconds)
                resp.raise_for_status()
                payload = resp.json()
            except Exception as exc:  # noqa: BLE001
                self.errors.append(f"remotive:{query!r}: {type(exc).__name__}: {exc}")
                continue
            for item in payload.get("jobs", []):
                job = self._map(item)
                if job is not None and job.canonical_key not in seen:
                    seen.add(job.canonical_key)
                    jobs.append(job)
        return jobs

    def _map(self, item: dict[str, Any]) -> Job | None:
        title = str(item.get("title") or "").strip()
        company = str(item.get("company_name") or "").strip()
        url = str(item.get("url") or "")
        if not title or not company or not url:
            return None
        description = _strip_html(item.get("description"))
        blob = f"{title} {item.get('category', '')} {description}"
        if _keyword_hits(blob, self.keywords) < self.min_keyword_hits:
            return None
        return Job(
            source=self.name,
            source_job_id=str(item.get("id")),
            company=company,
            title=title,
            location=str(item.get("candidate_required_location") or "Remote") or "Remote",
            description=description,
            url=url,
            posted_at=_parse_dt(item.get("publication_date")),
            fetched_at=datetime.now(timezone.utc),
            employment_type=item.get("job_type"),
            department=item.get("category"),
            raw={"tags": item.get("tags")},
        )


class ArbeitnowSource:
    """https://www.arbeitnow.com/api/job-board-api - single page, no auth, no query params."""

    name = "arbeitnow"
    _URL = "https://www.arbeitnow.com/api/job-board-api"

    def __init__(self, config: dict[str, Any] | None = None, *, session: Any | None = None, timeout_seconds: int = 20):
        self.config = config or {}
        self.enabled = bool(self.config.get("enabled", False))
        self.keywords = [k.lower() for k in self.config.get("keywords", _DEFAULT_KEYWORDS)]
        self.min_keyword_hits = int(self.config.get("min_keyword_hits", 1))
        self.timeout_seconds = timeout_seconds
        self._session = session or requests
        self.errors: list[str] = []

    def fetch(self) -> list[Job]:
        self.errors = []
        if not self.enabled:
            return []
        try:
            resp = self._session.get(self._URL, headers=_HEADERS, timeout=self.timeout_seconds)
            resp.raise_for_status()
            payload = resp.json()
        except Exception as exc:  # noqa: BLE001
            self.errors.append(f"arbeitnow: {type(exc).__name__}: {exc}")
            return []

        jobs: list[Job] = []
        for item in payload.get("data", []):
            job = self._map(item)
            if job is not None:
                jobs.append(job)
        return jobs

    def _map(self, item: dict[str, Any]) -> Job | None:
        title = str(item.get("title") or "").strip()
        company = str(item.get("company_name") or "").strip()
        url = str(item.get("url") or "")
        if not title or not company or not url:
            return None
        description = _strip_html(item.get("description"))
        tags = " ".join(str(t) for t in (item.get("tags") or []))
        blob = f"{title} {tags} {description}"
        if _keyword_hits(blob, self.keywords) < self.min_keyword_hits:
            return None
        created = item.get("created_at")
        posted_at = None
        if isinstance(created, (int, float)):
            posted_at = datetime.fromtimestamp(created, tz=timezone.utc)
        return Job(
            source=self.name,
            source_job_id=str(item.get("slug") or url),
            company=company,
            title=title,
            location=str(item.get("location") or ("Remote" if item.get("remote") else "")) or None,
            description=description,
            url=url,
            posted_at=posted_at,
            fetched_at=datetime.now(timezone.utc),
            employment_type=",".join(item.get("job_types") or []) or None,
            raw={"tags": item.get("tags")},
        )
