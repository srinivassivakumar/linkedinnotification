from __future__ import annotations

from datetime import datetime, timezone

from orchestrator.models import Job
from orchestrator.scorer import score_job


PREFERENCES = {
    "freshness": {"max_age_hours": 168, "strong_age_hours": 24},
    "seniority": {"max_years": 3},
    "locations": {"preferred": ["Pune", "Remote India"]},
    "keywords": {"strong": ["Python", "Linux", "Docker", "Kubernetes", "Git", "CI/CD"], "useful": ["Terraform"]},
    "scoring": {"strong_candidate": 68, "review": 55},
}
EVIDENCE = [
    {"id": "infra", "verified": True, "technologies": ["Python", "Linux", "Docker"]},
    {"id": "k8s", "verified": False, "technologies": ["Kubernetes"]},
]


def test_score_has_breakdown_and_matched_verified_evidence() -> None:
    job = Job(
        source="fixture",
        source_job_id="1",
        company="Acme",
        title="Associate MLOps Engineer",
        location="Pune",
        description="Python Linux Docker Kubernetes Git CI/CD Terraform platform automation " * 12,
        url="https://jobs.example.com/1",
        posted_at=datetime(2026, 9, 8, 8, tzinfo=timezone.utc),
    )
    score = score_job(job, PREFERENCES, EVIDENCE, now=datetime(2026, 9, 8, 12, tzinfo=timezone.utc))
    assert score.pre_score >= 68
    assert score.bucket == "strong_candidate"
    assert "infra" in score.matched_evidence_ids
    assert "python" in score.matched_terms
    assert set(score.signals) >= {"freshness", "seniority", "location", "evidence_overlap"}

