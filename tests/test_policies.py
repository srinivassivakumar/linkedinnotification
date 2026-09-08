from __future__ import annotations

from orchestrator.models import Job
from orchestrator.policies import apply_conservative_filters, location_decision, seniority_decision


PREFERENCES = {
    "locations": {"preferred": ["Pune", "Remote India"], "allowed_country": ["India"]},
    "seniority": {"max_years": 3, "reject_titles": ["Staff", "Principal", "Director"]},
    "role_families": ["devops", "cloud", "platform", "mlops", "infrastructure"],
}


def test_unknown_location_survives_with_warning() -> None:
    job = Job(source="fixture", source_job_id="1", company="Acme", title="DevOps Engineer", url="https://example.com")
    decision = location_decision(job, PREFERENCES)
    assert decision.keep is True
    assert decision.warnings


def test_clear_wrong_country_rejected() -> None:
    job = Job(source="fixture", source_job_id="1", company="Acme", title="DevOps Engineer", location="United States onsite", url="https://example.com")
    assert location_decision(job, PREFERENCES).keep is False


def test_hard_senior_title_rejected() -> None:
    job = Job(source="fixture", source_job_id="1", company="Acme", title="Principal Platform Engineer", location="Pune", url="https://example.com")
    assert seniority_decision(job, PREFERENCES).keep is False


def test_conservative_filters_keep_unknown_freshness() -> None:
    job = Job(source="fixture", source_job_id="1", company="Acme", title="Cloud Platform Engineer", location="Remote India", url="https://example.com")
    keep, warnings, _ = apply_conservative_filters(job, PREFERENCES, live_status="unknown", freshness="unknown")
    assert keep is True
    assert "freshness unknown" in warnings

