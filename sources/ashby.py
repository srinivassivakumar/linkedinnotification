from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import requests

from orchestrator.models import Job


class AshbySource:
    name = "ashby"

    def __init__(self, companies: list[str], timeout_seconds: int = 15):
        self.companies = companies
        self.timeout_seconds = timeout_seconds

    def fetch(self) -> list[Job]:
        jobs: list[Job] = []
        for company in self.companies:
            try:
                jobs.extend(self._fetch_company(company))
            except requests.RequestException as exc:
                print(f"ashby:{company}: {exc}", flush=True)
        return jobs

    def _fetch_company(self, company: str) -> list[Job]:
        url = f"https://api.ashbyhq.com/posting-api/job-board/{company}"
        response = requests.get(url, timeout=self.timeout_seconds)
        response.raise_for_status()
        payload = response.json()
        fetched_at = datetime.now(timezone.utc)
        return [self._map_job(company, item, fetched_at) for item in payload.get("jobs", [])]

    def _map_job(self, company: str, item: dict[str, Any], fetched_at: datetime) -> Job:
        return Job(
            source=self.name,
            source_job_id=str(item.get("id") or item.get("jobId")),
            company=company,
            title=item.get("title") or "",
            location=item.get("locationName") or item.get("location"),
            description=item.get("descriptionPlain") or item.get("descriptionHtml") or "",
            url=item.get("jobUrl") or item.get("applyUrl") or "",
            posted_at=_parse_datetime(item.get("publishedAt") or item.get("postedAt")),
            fetched_at=fetched_at,
            employment_type=item.get("employmentType"),
            department=item.get("departmentName"),
            raw=item,
        )


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None

