from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from orchestrator.models import FilterDecision, Job


ROOT = Path(__file__).resolve().parents[1]
HARD_SENIOR_TERMS = {"staff", "principal", "director", "head of", "vp", "vice president"}
SOFT_SENIOR_TERMS = {"senior", "lead", "manager"}


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def load_preferences(path: Path | None = None) -> dict[str, Any]:
    return load_yaml(path or ROOT / "profile" / "preferences.yaml")


def load_evidence(path: Path | None = None) -> list[dict[str, Any]]:
    data = load_yaml(path or ROOT / "profile" / "evidence_bank.yaml")
    return [item for item in data.get("evidence", []) if item.get("verified") is True]


def normalize_text(value: str | None) -> str:
    return " ".join((value or "").split()).strip()


def matching_text(job: Job) -> str:
    return f"{job.title} {job.company} {job.location or ''} {job.description}".lower()


def location_decision(job: Job, preferences: dict[str, Any]) -> FilterDecision:
    location = (job.location or "").lower()
    if not location:
        return FilterDecision(keep=True, stage="location", reason="unknown_location", warnings=["location unknown"])
    preferred = [item.lower() for item in preferences.get("locations", {}).get("preferred", [])]
    allowed = [item.lower() for item in preferences.get("locations", {}).get("allowed_country", [])]
    if "remote" in location and ("india" in location or not allowed):
        return FilterDecision(keep=True, stage="location", reason="remote_india_or_unknown")
    if any(item.lower() in location for item in preferred):
        return FilterDecision(keep=True, stage="location", reason="preferred_location")
    if allowed and not any(country in location for country in allowed):
        clear_foreign = any(term in location for term in ["united states", "usa", "us only", "canada", "europe", "germany", "uk"])
        if clear_foreign:
            return FilterDecision(keep=False, stage="location", reason="wrong_country")
    return FilterDecision(keep=True, stage="location", reason="location_uncertain", warnings=["location not clearly preferred"])


def seniority_decision(job: Job, preferences: dict[str, Any]) -> FilterDecision:
    text = matching_text(job)
    title = job.title.lower()
    reject_terms = [term.lower() for term in preferences.get("seniority", {}).get("reject_titles", [])]
    if any(term in title for term in reject_terms) or any(term in title for term in HARD_SENIOR_TERMS):
        return FilterDecision(keep=False, stage="seniority", reason="senior_title_rejected")
    max_years = int(preferences.get("seniority", {}).get("max_years", 3))
    years = [int(match) for match in re.findall(r"(\d+)\+?\s*(?:years|yrs)", text)]
    if years and min(years) > max_years:
        return FilterDecision(keep=False, stage="seniority", reason="experience_requirement_too_high")
    if any(term in title for term in SOFT_SENIOR_TERMS):
        return FilterDecision(keep=True, stage="seniority", reason="soft_seniority_uncertain", warnings=["seniority title needs review"])
    return FilterDecision(keep=True, stage="seniority", reason="seniority_realistic")


def role_family_decision(job: Job, preferences: dict[str, Any]) -> FilterDecision:
    text = matching_text(job)
    families = [item.lower() for item in preferences.get("role_families", [])]
    role_terms = set(families)
    role_terms.update({"devops", "cloud", "platform", "sre", "mlops", "infrastructure", "site reliability", "data engineer"})
    if any(term in text for term in role_terms):
        return FilterDecision(keep=True, stage="role_family", reason="role_family_match")
    return FilterDecision(keep=False, stage="role_family", reason="role_family_mismatch")


def apply_conservative_filters(job: Job, preferences: dict[str, Any], live_status: str, freshness: str) -> tuple[bool, list[str], list[FilterDecision]]:
    decisions: list[FilterDecision] = []
    warnings: list[str] = []

    if live_status == "dead":
        decisions.append(FilterDecision(keep=False, stage="live_check", reason="dead_listing"))
        return False, warnings, decisions
    if live_status == "unknown":
        warnings.append("live status unknown")

    if freshness == "stale":
        decisions.append(FilterDecision(keep=False, stage="freshness", reason="stale_posting"))
        return False, warnings, decisions
    if freshness == "unknown":
        warnings.append("freshness unknown")

    for decision in (location_decision(job, preferences), seniority_decision(job, preferences), role_family_decision(job, preferences)):
        decisions.append(decision)
        warnings.extend(decision.warnings)
        if not decision.keep:
            return False, warnings, decisions
    return True, warnings, decisions

