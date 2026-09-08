from __future__ import annotations

from datetime import datetime, timezone

from orchestrator.freshness import freshness_status
from orchestrator.models import Job


def _job(posted_at):
    return Job(
        source="fixture",
        source_job_id="1",
        company="Acme",
        title="DevOps Engineer",
        url="https://example.com/job",
        posted_at=posted_at,
    )


def test_freshness_statuses() -> None:
    now = datetime(2026, 9, 8, 12, tzinfo=timezone.utc)
    assert freshness_status(_job(datetime(2026, 9, 8, 1, tzinfo=timezone.utc)), now) == "fresh"
    assert freshness_status(_job(datetime(2026, 9, 5, 1, tzinfo=timezone.utc)), now) == "acceptable"
    assert freshness_status(_job(datetime(2026, 8, 1, 1, tzinfo=timezone.utc)), now) == "stale"
    assert freshness_status(_job(None), now) == "unknown"

