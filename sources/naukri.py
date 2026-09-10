"""Naukri support - strictly parse-and-prepare, never automate.

Allowed: parse Naukri job-alert emails, accept manually supplied Naukri URLs,
score them, and prepare a Telegram card with OPEN/APPLY links for manual action.

Forbidden (do not add): login automation, browser automation, auto-apply,
CAPTCHA handling, bot evasion, automated Naukri messaging, or scraping Naukri
pages. If Apify is ever used for Naukri discovery, do actor discovery only and
review legality/ToS/pricing/schema before any run.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from orchestrator.models import Job

_NAUKRI_JOB_RE = re.compile(r"naukri\.com/(?:job-listings|jobs|job)", re.IGNORECASE)


def job_from_manual(
    url: str,
    title: str,
    company: str,
    description: str = "",
    location: str | None = None,
    source_job_id: str | None = None,
) -> Job:
    """Build a Job from a URL + fields the user supplies by hand."""
    if not _NAUKRI_JOB_RE.search(url) and "naukri.com" not in url.lower():
        raise ValueError("job_from_manual expects a naukri.com job URL")
    slug = source_job_id or re.sub(r"[^a-z0-9]+", "-", (url.split("naukri.com/")[-1]).lower()).strip("-")[:60]
    return Job(
        source="naukri",
        source_job_id=slug or "manual",
        company=company,
        title=title,
        location=location,
        description=description,
        url=url,
        posted_at=datetime.now(timezone.utc),
        raw={"entry": "manual"},
    )


def jobs_from_alert_email(html: str) -> list[Job]:
    """Best-effort extraction of job links + titles from a Naukri alert email."""
    soup = BeautifulSoup(html or "", "html.parser")
    jobs: list[Job] = []
    seen: set[str] = set()
    for tag in soup.find_all("a", href=True):
        href = tag["href"]
        if not _NAUKRI_JOB_RE.search(href):
            continue
        clean = href.split("?")[0]
        if clean in seen:
            continue
        seen.add(clean)
        title = " ".join(tag.get_text(" ", strip=True).split()) or "Naukri role"
        slug = re.sub(r"[^a-z0-9]+", "-", clean.split("naukri.com/")[-1].lower()).strip("-")[:60]
        jobs.append(
            Job(
                source="naukri",
                source_job_id=slug or f"alert-{len(jobs)}",
                company="(from Naukri alert - confirm)",
                title=title,
                url=clean,
                description="",
                posted_at=datetime.now(timezone.utc),
                raw={"entry": "alert_email"},
            )
        )
    return jobs
