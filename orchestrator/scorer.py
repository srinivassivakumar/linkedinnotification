from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from orchestrator.freshness import freshness_status
from orchestrator.models import Job, ScoreResult


def _terms(preferences: dict[str, Any], evidence: list[dict[str, Any]]) -> set[str]:
    values: set[str] = set()
    for key in ("strong", "useful"):
        values.update(item.lower() for item in preferences.get("keywords", {}).get(key, []))
    for item in evidence:
        values.update(str(term).lower() for term in item.get("technologies", []))
    return {term for term in values if term}


def _contains_term(text: str, term: str) -> bool:
    if "/" in term or "+" in term:
        return term in text
    return re.search(rf"\b{re.escape(term)}\b", text) is not None


def score_job(
    job: Job,
    preferences: dict[str, Any],
    evidence: list[dict[str, Any]] | None = None,
    warnings: list[str] | None = None,
    now: datetime | None = None,
) -> ScoreResult:
    verified_evidence = evidence or []
    warnings_out = list(warnings or [])
    text = f"{job.title} {job.location or ''} {job.description}".lower()
    current = now or datetime.now(timezone.utc)
    freshness_cfg = preferences.get("freshness", {})
    freshness = freshness_status(
        job,
        current,
        int(freshness_cfg.get("max_age_hours", 168)),
        int(freshness_cfg.get("strong_age_hours", 24)),
    )
    freshness_points = {"fresh": 15, "acceptable": 9, "unknown": 5, "stale": 0}[freshness]

    seniority_points = 15
    title = job.title.lower()
    if any(term in title for term in ["senior", "lead", "manager"]):
        seniority_points = 8
    if any(term in title for term in ["staff", "principal", "director", "head of", "vp"]):
        seniority_points = 0
    years = [int(match) for match in re.findall(r"(\d+)\+?\s*(?:years|yrs)", text)]
    max_years = int(preferences.get("seniority", {}).get("max_years", 3))
    if years and min(years) > max_years:
        seniority_points = min(seniority_points, 4)

    location = (job.location or "").lower()
    preferred = [item.lower() for item in preferences.get("locations", {}).get("preferred", [])]
    location_points = 5
    if not location:
        warnings_out.append("location unknown")
    elif any(item in location for item in preferred) or ("remote" in location and "india" in location):
        location_points = 10
    elif "india" in location:
        location_points = 7

    matched_terms = sorted(term for term in _terms(preferences, verified_evidence) if _contains_term(text, term))
    evidence_points = min(25, len(matched_terms) * 4)
    matched_evidence_ids: list[str] = []
    for item in verified_evidence:
        techs = [str(term).lower() for term in item.get("technologies", [])]
        if any(term in matched_terms for term in techs):
            matched_evidence_ids.append(str(item.get("id")))

    description_words = len(job.description.split())
    posting_quality = 5 if description_words >= 120 else (3 if description_words >= 40 else 1)
    application_friction = 5 if any(term in job.url.lower() for term in ["greenhouse", "lever", "ashby", "jobs"]) else 2
    human_path = 0

    signals = {
        "freshness": freshness_points,
        "seniority": seniority_points,
        "location": location_points,
        "evidence_overlap": evidence_points,
        "posting_quality": posting_quality,
        "application_friction": application_friction,
        "human_path": human_path,
        "reserved_subjective_capacity": 0,
    }
    pre_score = min(80, sum(signals.values()))
    thresholds = preferences.get("scoring", {})
    if pre_score >= int(thresholds.get("strong_candidate", 68)):
        bucket = "strong_candidate"
    elif pre_score >= int(thresholds.get("review", 55)):
        bucket = "review"
    else:
        bucket = "weak"
    if freshness == "unknown":
        warnings_out.append("freshness unknown")
    return ScoreResult(
        pre_score=pre_score,
        bucket=bucket,
        signals=signals,
        matched_evidence_ids=sorted(set(matched_evidence_ids)),
        matched_terms=matched_terms,
        warnings=sorted(set(warnings_out)),
    )

