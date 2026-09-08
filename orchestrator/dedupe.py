from __future__ import annotations

import hashlib
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from orchestrator.models import Job
from orchestrator.policies import normalize_text


TRACKING_PARAMS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "gh_src"}


def normalize_url(url: str) -> str:
    parsed = urlparse(url.strip())
    query = urlencode([(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True) if k.lower() not in TRACKING_PARAMS])
    path = parsed.path.rstrip("/") or "/"
    return urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), path, "", query, ""))


def fingerprint(job: Job) -> str:
    company = normalize_text(job.company).lower()
    title = normalize_text(job.title).lower()
    location = normalize_text(job.location or "").lower()
    digest = hashlib.sha1(normalize_text(job.description).lower().encode("utf-8")).hexdigest()[:12]
    return f"{company}|{title}|{location}|{digest}"


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
        if key in seen_keys or url in seen_urls or fp in seen_fingerprints:
            duplicates += 1
            continue
        seen_keys.add(key)
        seen_urls.add(url)
        seen_fingerprints.add(fp)
        unique.append(job)
    return unique, duplicates

