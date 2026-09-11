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
_CUTSHORT = re.compile(r"cutshort\.io/job/([a-z0-9\-]+)", re.IGNORECASE)

# ATS domains Google Alerts links are recognized against, so those jobs are
# handed to the same ``source`` name as the direct ATS adapter (dedupe then
# merges them on canonical URL / company+title+location instead of doubling up).
_ATS_DOMAIN_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("greenhouse", re.compile(r"(?:boards\.greenhouse\.io|job-boards\.greenhouse\.io)/([a-z0-9\-]+)/jobs/(\w+)", re.IGNORECASE)),
    ("lever", re.compile(r"jobs\.lever\.co/([a-z0-9\-]+)/([a-f0-9\-]{8,})", re.IGNORECASE)),
    ("ashby", re.compile(r"jobs\.ashbyhq\.com/([a-z0-9\-]+)/([a-f0-9\-]{8,})", re.IGNORECASE)),
    ("workday", re.compile(r"([a-z0-9\-]+)\.wd\d+\.myworkdayjobs\.com/(?:[a-zA-Z\-]+/)?([a-zA-Z0-9_\-]+)/job/", re.IGNORECASE)),
    ("smartrecruiters", re.compile(r"jobs\.smartrecruiters\.com/([a-zA-Z0-9\-]+)/(\w+)", re.IGNORECASE)),
]


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


def jobs_from_cutshort_alert(html: str, text: str = "") -> list[Job]:
    soup = _soup(html, text)
    jobs: list[Job] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        m = _CUTSHORT.search(a["href"])
        if not m or m.group(1) in seen:
            continue
        slug = m.group(1)
        title = _clean(a.get_text(" ", strip=True))
        if not title or len(title) < 3:
            continue
        seen.add(slug)
        jobs.append(Job(
            source="cutshort",
            source_job_id=slug,
            company="(from Cutshort alert - confirm)",
            title=title,
            location=None,
            description="",
            url=f"https://cutshort.io/job/{slug}",
            posted_at=_now(),
            raw={"entry": "cutshort_alert_email"},
        ))
    return jobs


def unwrap_google_redirect(href: str) -> str:
    """Google Alerts wraps every link in a ``google.com/url?q=<target>&...``
    redirect (occasionally ``https://www.google.com/aclk?...`` for ad slots,
    which is skipped by callers since it carries no useful ``q``). Return the
    unwrapped target, or ``href`` unchanged if it isn't a Google redirect."""
    parsed = urlparse(href)
    if "google." not in parsed.netloc.lower() or parsed.path not in {"/url", "/aclk"}:
        return href
    qs = parse_qs(parsed.query)
    target = (qs.get("q") or qs.get("url") or [None])[0]
    return target or href


def _ats_match(url: str) -> tuple[str, str, str] | None:
    """(source_name, company_slug, source_job_id) for a recognized ATS URL."""
    for name, pattern in _ATS_DOMAIN_PATTERNS:
        m = pattern.search(url)
        if m:
            return name, m.group(1), m.group(2)
    return None


def jobs_from_google_alert(html: str, text: str = "") -> list[Job]:
    """Google Alerts emails are mostly links to news/blog/career pages, not a
    structured job feed. We only keep links that resolve (after unwrapping the
    Google redirect) to a recognized ATS job-posting URL, and hand those to a
    Job shaped like the direct ATS adapter's output (same ``source`` name) so
    dedupe merges it with anything the ATS source itself already found.
    Everything else in the alert is noise for job discovery and is dropped."""
    soup = _soup(html, text)
    jobs: list[Job] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        target = unwrap_google_redirect(a["href"])
        match = _ats_match(target)
        if not match:
            continue
        source_name, company_slug, job_id = match
        key = f"{source_name}:{job_id}"
        if key in seen:
            continue
        title = _clean(a.get_text(" ", strip=True))
        if not title or len(title) < 3:
            continue
        seen.add(key)
        jobs.append(Job(
            source=source_name,
            source_job_id=job_id,
            company=company_slug.replace("-", " ").title(),
            title=title,
            location=None,
            description="",
            url=target.split("?")[0],
            posted_at=_now(),
            raw={"entry": "google_alert_email", "ats_platform": source_name},
        ))
    return jobs


_PARSERS: dict[str, Callable[[str, str], list[Job]]] = {
    "linkedin": jobs_from_linkedin_alert,
    "indeed": jobs_from_indeed_alert,
    "instahyre": jobs_from_instahyre_alert,
    "cutshort": jobs_from_cutshort_alert,
    "google_alerts": jobs_from_google_alert,
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
    if "cutshort" in blob:
        return "cutshort"
    if ("googlealerts-noreply@google.com" in blob or "google alert" in blob) and "google" in blob:
        return "google_alerts"
    return None


def jobs_from_alert(sender: str, subject: str, html: str, text: str = "") -> tuple[str | None, list[Job]]:
    provider = alert_provider(sender, subject)
    if provider is None:
        return None, []
    return provider, _PARSERS[provider](html, text)
