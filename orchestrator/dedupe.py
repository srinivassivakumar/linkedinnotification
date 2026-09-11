from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from orchestrator.models import Job
from orchestrator.policies import normalize_text

# Matching keys, in precedence order:
#   1. canonical_key   -- "source:source_job_id" (exact, same source re-fetched)
#   2. normalized URL  -- same posting reached via a different source/email
#      (tracking/redirect params stripped, host+path only)
#   3. company+title+location fallback -- the same role discovered through
#      channels that don't share a URL or id at all (e.g. a LinkedIn alert
#      email with a placeholder company vs. the same role via Greenhouse).
#      This tier deliberately ignores the job description, since alert-email
#      snippets and full ATS descriptions for the *same* posting never read
#      identically -- matching on description would just fail to merge.
#      It intentionally does NOT fire when company/title/location themselves
#      differ, so two distinct openings with different titles are kept apart.
TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "gh_src", "gh_jid", "trk", "trkEmail", "ref", "refId", "referrer",
    "source", "from", "originalSubdomain", "position", "pageNum", "s",
    "lever-origin", "lever-source",
}

# Placeholder companies that alert-email parsers use when the email markup
# doesn't reliably expose the company name (see sources/job_alert_emails.py,
# sources/naukri.py). A job stuck with one of these can only ever be merged
# via canonical_key or URL -- never via the company+title+location fallback,
# since "confirm" would otherwise match every unrelated placeholder job with
# the same title.
_PLACEHOLDER_COMPANY_RE = re.compile(r"\(from .* alert - confirm\)|\(company (?:from|via) .* - confirm\)", re.IGNORECASE)


def normalize_url(url: str) -> str:
    parsed = urlparse(url.strip())
    query = urlencode([(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True) if k.lower() not in TRACKING_PARAMS])
    path = parsed.path.rstrip("/") or "/"
    return urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), path, "", query, ""))


def _normalize_role_text(value: str) -> str:
    """Lowercase, strip punctuation/seniority noise so e.g. 'Sr. ML Engineer'
    and 'Senior ML Engineer' land on the same key."""
    text = normalize_text(value).lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def fingerprint(job: Job) -> str | None:
    """Company+title+location fallback key, or ``None`` if the company is a
    known placeholder (too weak to safely merge on)."""
    if _PLACEHOLDER_COMPANY_RE.search(job.company or ""):
        return None
    company = _normalize_role_text(job.company)
    title = _normalize_role_text(job.title)
    location = _normalize_role_text(job.location or "")
    if not company or not title:
        return None
    return f"{company}|{title}|{location}"


def dedupe_jobs(jobs: list[Job]) -> tuple[list[Job], int]:
    seen_keys: set[str] = set()
    seen_urls: set[str] = set()
    seen_fingerprints: set[str] = set()
    unique: list[Job] = []
    duplicates = 0
    for job in jobs:
        key = job.canonical_key
        url = normalize_url(job.url)
        fp = fingerprint(job)
        if key in seen_keys or url in seen_urls or (fp is not None and fp in seen_fingerprints):
            duplicates += 1
            continue
        seen_keys.add(key)
        seen_urls.add(url)
        if fp is not None:
            seen_fingerprints.add(fp)
        unique.append(job)
    return unique, duplicates

