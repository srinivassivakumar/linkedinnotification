from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import requests

from orchestrator.models import Job


class LeverSource:
    name = "lever"

    def __init__(self, companies: list[str], timeout_seconds: int = 15):
        self.companies = companies
        self.timeout_seconds = timeout_seconds
        self.errors: list[str] = []

    def fetch(self) -> list[Job]:
        jobs: list[Job] = []
        self.errors = []
        for company in self.companies:
            try:
                jobs.extend(self._fetch_company(company))
            except Exception as exc:  # noqa: BLE001 - one bad company must not break the scan
                message = f"lever:{company}: {type(exc).__name__}: {exc}"
                self.errors.append(message)
                print(message, flush=True)
        return jobs

    def _fetch_company(self, company: str) -> list[Job]:
        url = f"https://api.lever.co/v0/postings/{company}"
        response = requests.get(url, params={"mode": "json"}, timeout=self.timeout_seconds)
        response.raise_for_status()
        fetched_at = datetime.now(timezone.utc)
        out: list[Job] = []
        for item in response.json():
            try:
                out.append(self._map_job(company, item, fetched_at))
            except Exception as exc:  # noqa: BLE001 - skip a single malformed posting
                self.errors.append(f"lever:{company}: skipped 1 posting: {type(exc).__name__}")
        return out

    def _map_job(self, company: str, item: dict[str, Any], fetched_at: datetime) -> Job:
        categories = item.get("categories") or {}
        return Job(
            source=self.name,
            source_job_id=str(item.get("id")),
            company=company,
            title=item.get("text") or "",
            location=categories.get("location"),
            description=item.get("descriptionPlain") or item.get("description") or "",
            url=item.get("hostedUrl") or item.get("applyUrl") or "",
            posted_at=_from_millis(item.get("createdAt") or item.get("listedAt")),
            fetched_at=fetched_at,
            employment_type=categories.get("commitment"),
            department=categories.get("team") or categories.get("department"),
            raw=item,
        )


def _from_millis(value: Any) -> datetime | None:
    if value in {None, ""}:
        return None
    try:
        return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None

