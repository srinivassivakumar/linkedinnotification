"""SmartRecruiters postings source - free, official, no key.

    GET https://api.smartrecruiters.com/v1/companies/{identifier}/postings?limit=100
    GET https://api.smartrecruiters.com/v1/companies/{identifier}/postings/{id}

The company identifier is the slug in ``careers.smartrecruiters.com/{identifier}``.
Configure them in ``config/sources.yaml`` under
``sources.ats.smartrecruiters.companies`` as a plain list of identifiers.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

import requests

from orchestrator.models import Job

_BASE = "https://api.smartrecruiters.com/v1/companies"
_HEADERS = {"User-Agent": "Mozilla/5.0 career-agent", "Accept": "application/json"}


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


class SmartRecruitersSource:
    name = "smartrecruiters"

    def __init__(self, companies: list[str] | None, timeout_seconds: int = 20, per_company_limit: int = 100, fetch_details: bool = True):
        self.companies = companies or []
        self.timeout_seconds = timeout_seconds
        self.per_company_limit = per_company_limit
        self.fetch_details = fetch_details
        self.errors: list[str] = []

    def fetch(self) -> list[Job]:
        jobs: list[Job] = []
        self.errors = []
        for company in self.companies:
            try:
                jobs.extend(self._fetch_company(company))
            except Exception as exc:  # noqa: BLE001 - one bad company must not break the scan
                message = f"smartrecruiters:{company}: {type(exc).__name__}: {exc}"
                self.errors.append(message)
                print(message, flush=True)
        return jobs

    def _fetch_company(self, company: str) -> list[Job]:
        resp = requests.get(
            f"{_BASE}/{company}/postings",
            params={"limit": self.per_company_limit},
            headers=_HEADERS,
            timeout=self.timeout_seconds,
        )
        resp.raise_for_status()
        content = resp.json().get("content", [])
        fetched_at = datetime.now(timezone.utc)
        out: list[Job] = []
        for item in content:
            try:
                out.append(self._map_job(company, item, fetched_at))
            except Exception as exc:  # noqa: BLE001 - skip a single malformed posting
                self.errors.append(f"smartrecruiters:{company}: skipped 1 posting: {type(exc).__name__}")
        return out

    def _map_job(self, company: str, item: dict[str, Any], fetched_at: datetime) -> Job:
        loc = item.get("location") or {}
        location = loc.get("fullLocation") or ", ".join(
            p for p in [loc.get("city"), loc.get("region"), loc.get("country")] if p
        )
        if loc.get("remote"):
            location = f"Remote - {location}" if location else "Remote"
        posting_id = str(item.get("id"))
        company_id = (item.get("company") or {}).get("identifier") or company
        description = ""
        if self.fetch_details:
            try:
                d = requests.get(f"{_BASE}/{company_id}/postings/{posting_id}", headers=_HEADERS, timeout=self.timeout_seconds)
                if d.ok:
                    sections = ((d.json().get("jobAd") or {}).get("sections")) or {}
                    description = " ".join(
                        re.sub(r"<[^>]+>", " ", (sections.get(k) or {}).get("text", "") or "")
                        for k in ("jobDescription", "qualifications", "additionalInformation")
                    ).strip()
            except Exception:  # noqa: BLE001 - detail is best-effort
                pass
        return Job(
            source=self.name,
            source_job_id=posting_id,
            company=(item.get("company") or {}).get("name") or company,
            title=item.get("name") or "",
            location=location or None,
            description=description,
            url=f"https://careers.smartrecruiters.com/{company_id}/{posting_id}",
            posted_at=_parse_dt(item.get("releasedDate") or item.get("createdOn")),
            fetched_at=fetched_at,
            employment_type=(item.get("typeOfEmployment") or {}).get("label"),
            department=(item.get("department") or {}).get("label"),
            raw={"experienceLevel": (item.get("experienceLevel") or {}).get("label"), "refNumber": item.get("refNumber")},
        )
