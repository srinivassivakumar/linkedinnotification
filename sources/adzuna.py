"""Adzuna source - official API, free tier.

Needs free credentials from https://developer.adzuna.com (``ADZUNA_APP_ID`` +
``ADZUNA_APP_KEY`` in ``.env``). Free tier is ~250 calls/month, 25 hits/minute -
plenty for a few keyword queries a day. Disabled automatically if the
credentials are missing.

    GET https://api.adzuna.com/v1/api/jobs/in/search/1
        ?app_id=...&app_key=...&results_per_page=50&what=...&max_days_old=7&sort_by=date

The ``in`` in the path is the India index; ``content-type: application/json``.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import requests

from orchestrator.models import Job

_BASE = "https://api.adzuna.com/v1/api/jobs"


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


class AdzunaSource:
    name = "adzuna"

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        *,
        app_id: str | None = None,
        app_key: str | None = None,
        session: Any | None = None,
    ) -> None:
        self.config = config or {}
        self.enabled = bool(self.config.get("enabled", True))
        self.app_id = app_id if app_id is not None else os.getenv("ADZUNA_APP_ID", "")
        self.app_key = app_key if app_key is not None else os.getenv("ADZUNA_APP_KEY", "")
        self.country = str(self.config.get("country", "in"))
        self.results_per_page = int(self.config.get("results_per_page", 50))
        self.max_days_old = int(self.config.get("max_days_old", 7))
        self.queries = self.config.get("queries") or ["AI engineer", "machine learning engineer", "data engineer"]
        self.timeout_seconds = int(self.config.get("timeout_seconds", 20))
        self._session = session or requests
        self.errors: list[str] = []

    def fetch(self) -> list[Job]:
        self.errors = []
        if not self.enabled:
            return []
        if not (self.app_id and self.app_key):
            self.errors.append("adzuna: ADZUNA_APP_ID / ADZUNA_APP_KEY not set; skipped")
            print("adzuna: credentials not set; skipped", flush=True)
            return []

        jobs: list[Job] = []
        seen: set[str] = set()
        for query in self.queries:
            try:
                for item in self._search(query):
                    job = self._map_job(item)
                    if job and job.canonical_key not in seen:
                        seen.add(job.canonical_key)
                        jobs.append(job)
            except Exception as exc:  # noqa: BLE001 - one query must not break the scan
                message = f"adzuna:{query!r}: {type(exc).__name__}: {exc}"
                self.errors.append(message)
                print(message, flush=True)
        return jobs

    def _search(self, query: str) -> list[dict[str, Any]]:
        resp = self._session.get(
            f"{_BASE}/{self.country}/search/1",
            params={
                "app_id": self.app_id,
                "app_key": self.app_key,
                "results_per_page": self.results_per_page,
                "what": query,
                "max_days_old": self.max_days_old,
                "sort_by": "date",
                "content-type": "application/json",
            },
            timeout=self.timeout_seconds,
        )
        resp.raise_for_status()
        return resp.json().get("results", [])

    def _map_job(self, item: dict[str, Any]) -> Job | None:
        title = str(item.get("title") or "").strip()
        url = item.get("redirect_url") or ""
        if not title or not url:
            return None
        loc = item.get("location") or {}
        location = loc.get("display_name") or ", ".join(loc.get("area", [])[-2:])
        return Job(
            source=self.name,
            source_job_id=str(item.get("id")),
            company=(item.get("company") or {}).get("display_name") or "(company via Adzuna)",
            title=title,
            location=location or None,
            description=str(item.get("description") or ""),
            url=url,
            posted_at=_parse_dt(item.get("created")),
            fetched_at=datetime.now(timezone.utc),
            employment_type=item.get("contract_time"),
            department=item.get("category", {}).get("label"),
            raw={"salary_min": item.get("salary_min"), "salary_max": item.get("salary_max")},
        )
