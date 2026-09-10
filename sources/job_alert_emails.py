"""Parse job-alert emails into Job objects - free, ToS-clean.

You subscribe to alerts on LinkedIn / Indeed / Instahyre (and Naukri, handled in
``sources.naukri``); the platforms email you matching jobs; the Gmail watcher
parses those emails here. No scraping, no login, no automation against the sites -
just reading mail you asked to receive.

Every parser is best-effort: alert-email HTML changes, so extract what is
reliably there (job URL + title + company/location when present) and let the
deterministic scorer + filters do the rest. The job URL carries a stable id per
platform, so a job that appears in several alerts is still surfaced once.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Callable
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup

from orchestrator.models import Job

_LINKEDIN_VIEW = re.compile(r"linkedin\.com/(?:comm/)?jobs/view/(\d+)", re.IGNORECASE)
_INDEED_JK = re.compile(r"[?&](?:jk|vjk)=([0-9a-f]{8,20})", re.IGNORECASE)
_INSTAHYRE = re.compile(r"instahyre\.com/(?:job|opportunity)/(\d+)", re.IGNORECASE)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _clean(text: str) -> str:
    return " ".join((text or "").split()).strip()


def _soup(html: str, text: str) -> BeautifulSoup:
    return BeautifulSoup(html or f"<pre>{text or ''}</pre>", "html.parser")


def jobs_from_linkedin_alert(html: str, text: str = "") -> list[Job]:
    soup = _soup(html, text)
    jobs: list[Job] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        m = _LINKEDIN_VIEW.search(a["href"])
        if not m or m.group(1) in seen:
            continue
        job_id = m.group(1)
        title = _clean(a.get_text(" ", strip=True))
        if not title or len(title) < 3:
            continue
        seen.add(job_id)
        # company/location usually sit in the next couple of text nodes
        tail = _clean(" ".join(s for s in a.find_parent().stripped_strings))[:200] if a.find_parent() else ""
        jobs.append(Job(
            source="linkedin",
            source_job_id=job_id,
            company="(from LinkedIn alert - confirm)",
            title=title,
            location=None,
            description=tail,
            url=f"https://www.linkedin.com/jobs/view/{job_id}/",
            posted_at=_now(),
            raw={"entry": "linkedin_alert_email"},
        ))
    return jobs


def jobs_from_indeed_alert(html: str, text: str = "") -> list[Job]:
    soup = _soup(html, text)
    jobs: list[Job] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        m = _INDEED_JK.search(a["href"])
        if not m or m.group(1) in seen:
            continue
        jk = m.group(1)
        title = _clean(a.get_text(" ", strip=True))
        if not title or title.lower() in {"apply now", "view job", "see job"}:
            continue
        seen.add(jk)
        jobs.append(Job(
            source="indeed",
            source_job_id=jk,
            company="(from Indeed alert - confirm)",
            title=title,
            location=None,
            description="",
            url=f"https://www.indeed.com/viewjob?jk={jk}",
            posted_at=_now(),
            raw={"entry": "indeed_alert_email"},
        ))
    return jobs


def jobs_from_instahyre_alert(html: str, text: str = "") -> list[Job]:
    soup = _soup(html, text)
    jobs: list[Job] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        m = _INSTAHYRE.search(a["href"])
        if not m or m.group(1) in seen:
            continue
        job_id = m.group(1)
        title = _clean(a.get_text(" ", strip=True))
        if not title or len(title) < 3:
            continue
        seen.add(job_id)
        jobs.append(Job(
            source="instahyre",
            source_job_id=job_id,
            company="(from Instahyre alert - confirm)",
            title=title,
            location=None,
            description="",
            url=a["href"].split("?")[0],
            posted_at=_now(),
            raw={"entry": "instahyre_alert_email"},
        ))
    return jobs


_PARSERS: dict[str, Callable[[str, str], list[Job]]] = {
    "linkedin": jobs_from_linkedin_alert,
    "indeed": jobs_from_indeed_alert,
    "instahyre": jobs_from_instahyre_alert,
}


def alert_provider(sender: str, subject: str) -> str | None:
    """Which alert parser (if any) handles this email."""
    blob = f"{sender} {subject}".lower()
    if "linkedin.com" in blob and ("job" in blob or "alert" in blob or "hiring" in blob):
        return "linkedin"
    if "indeed.com" in blob or "indeed job" in blob:
        return "indeed"
    if "instahyre" in blob:
        return "instahyre"
    return None


def jobs_from_alert(sender: str, subject: str, html: str, text: str = "") -> tuple[str | None, list[Job]]:
    provider = alert_provider(sender, subject)
    if provider is None:
        return None, []
    return provider, _PARSERS[provider](html, text)
