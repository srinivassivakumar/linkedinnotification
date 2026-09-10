"""Workday CXS source - free, official, no key.

Every Workday careers site exposes a JSON search endpoint:

    POST https://{host}/wday/cxs/{tenant}/{site}/jobs
    body: {"appliedFacets": {...}, "limit": 20, "offset": 0, "searchText": "..."}

and a matching detail endpoint ``GET .../wday/cxs/{tenant}/{site}{externalPath}``
for the full job description. No authentication, no rate limit worth worrying
about at this volume.

Configure companies in ``config/sources.yaml`` under
``sources.ats.workday.companies`` as::

    - name: NVIDIA
      host: nvidia.wd5.myworkdayjobs.com
      tenant: nvidia
      site: NVIDIAExternalCareerSite
      search_text: "engineer india"      # optional, narrows the search
      facets: {}                          # optional, passed as appliedFacets

The host/tenant/site are visible in the careers URL:
``https://{tenant}.wdN.myworkdayjobs.com/en-US/{site}``.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

from orchestrator.models import Job

_POSTED_RE = re.compile(r"(\d+)\+?\s*day", re.IGNORECASE)


def parse_posted_on(text: str | None, now: datetime | None = None) -> datetime | None:
    """Workday only gives relative text: 'Posted Today', 'Posted Yesterday',
    'Posted 5 Days Ago', 'Posted 30+ Days Ago'."""
    if not text:
        return None
    now = now or datetime.now(timezone.utc)
    low = text.lower()
    if "today" in low:
        return now
    if "yesterday" in low:
        return now - timedelta(days=1)
    match = _POSTED_RE.search(low)
    if match:
        return now - timedelta(days=int(match.group(1)))
    return None


class WorkdaySource:
    name = "workday"

    def __init__(self, companies: list[dict[str, Any]] | None, timeout_seconds: int = 20, per_company_limit: int = 20):
        self.companies = companies or []
        self.timeout_seconds = timeout_seconds
        self.per_company_limit = per_company_limit
        self.errors: list[str] = []

    def fetch(self) -> list[Job]:
        jobs: list[Job] = []
        self.errors = []
        for cfg in self.companies:
            if not cfg.get("enabled", True):
                continue
            try:
                jobs.extend(self._fetch_company(cfg))
            except Exception as exc:  # noqa: BLE001 - one bad tenant must not break the scan
                message = f"workday:{cfg.get('name', cfg.get('tenant', '?'))}: {type(exc).__name__}: {exc}"
                self.errors.append(message)
                print(message, flush=True)
        return jobs

    def _fetch_company(self, cfg: dict[str, Any]) -> list[Job]:
        host, tenant, site = cfg["host"], cfg["tenant"], cfg["site"]
        base = f"https://{host}/wday/cxs/{tenant}/{site}"
        body = {
            "appliedFacets": cfg.get("facets") or {},
            "limit": int(cfg.get("limit", self.per_company_limit)),
            "offset": 0,
            "searchText": cfg.get("search_text", ""),
        }
        headers = {"User-Agent": "Mozilla/5.0 career-agent", "Accept": "application/json"}
        resp = requests.post(f"{base}/jobs", json=body, headers=headers, timeout=self.timeout_seconds)
        resp.raise_for_status()
        payload = resp.json()
        company = cfg.get("name") or tenant
        fetched_at = datetime.now(timezone.utc)
        want_details = bool(cfg.get("fetch_details", True))

        out: list[Job] = []
        for item in payload.get("jobPostings", []):
            try:
                out.append(self._map_job(company, host, site, base, item, fetched_at, headers, want_details))
            except Exception as exc:  # noqa: BLE001 - skip a single malformed posting
                self.errors.append(f"workday:{company}: skipped 1 posting: {type(exc).__name__}")
        return out

    def _map_job(
        self,
        company: str,
        host: str,
        site: str,
        base: str,
        item: dict[str, Any],
        fetched_at: datetime,
        headers: dict[str, str],
        want_details: bool,
    ) -> Job:
        external_path = item.get("externalPath") or ""
        public_url = f"https://{host}/en-US/{site}{external_path}"
        description = ""
        job_id = external_path.rsplit("_", 1)[-1] or external_path
        if want_details and external_path:
            try:
                d = requests.get(f"{base}{external_path}", headers=headers, timeout=self.timeout_seconds)
                if d.ok:
                    info = d.json().get("jobPostingInfo", {})
                    description = re.sub(r"<[^>]+>", " ", info.get("jobDescription", "") or "")
                    job_id = info.get("jobPostingId") or job_id
            except Exception:  # noqa: BLE001 - detail is best-effort
                pass
        bullets = item.get("bulletFields") or []
        return Job(
            source=self.name,
            source_job_id=str(job_id),
            company=company,
            title=item.get("title") or "",
            location=item.get("locationsText"),
            description=description or " ".join(str(b) for b in bullets),
            url=public_url,
            posted_at=parse_posted_on(item.get("postedOn"), fetched_at),
            fetched_at=fetched_at,
            raw={"bulletFields": bullets, "postedOn": item.get("postedOn")},
        )
