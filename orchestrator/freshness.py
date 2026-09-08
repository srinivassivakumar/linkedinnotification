from __future__ import annotations

from datetime import datetime, timezone

from orchestrator.models import Job


def freshness_status(job: Job, now: datetime | None = None, max_age_hours: int = 168, strong_age_hours: int = 24) -> str:
    if job.posted_at is None:
        return "unknown"
    current = now or datetime.now(timezone.utc)
    posted_at = job.posted_at
    if posted_at.tzinfo is None:
        posted_at = posted_at.replace(tzinfo=timezone.utc)
    age_h = (current - posted_at).total_seconds() / 3600
    if age_h < 0:
        return "unknown"
    if age_h <= strong_age_hours:
        return "fresh"
    if age_h <= max_age_hours:
        return "acceptable"
    return "stale"

