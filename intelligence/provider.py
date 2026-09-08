from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from orchestrator.models import Candidate, Job


class IntelligenceProvider(ABC):
    @abstractmethod
    def evaluate_jobs(self, candidates: list[Candidate], evidence: list[dict[str, Any]]) -> list[Candidate]:
        raise NotImplementedError

    @abstractmethod
    def tailor_application(self, job: Job, evidence: list[dict[str, Any]]) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def classify_reply(self, message: Any) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def prepare_interview(self, application: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError


def candidate_payload(candidate: Candidate, evidence: list[dict[str, Any]]) -> dict[str, Any]:
    matched = set(candidate.score.matched_evidence_ids)
    return {
        "job_id": candidate.job.source_job_id,
        "job_key": candidate.job_key,
        "title": candidate.job.title,
        "company": candidate.job.company,
        "location": candidate.job.location,
        "url": candidate.job.url,
        "posted_at": candidate.job.posted_at.isoformat() if candidate.job.posted_at else None,
        "pre_analysis": candidate.score.model_dump(),
        "verified_evidence": [item for item in evidence if str(item.get("id")) in matched],
        "jd": candidate.job.description,
    }


def get_intelligence_provider(mode: str):
    normalized = (mode or "mock").strip().lower()
    if normalized == "mock":
        from intelligence.mock import MockProvider

        return MockProvider()
    if normalized == "claude":
        from intelligence.claude import ClaudeProvider

        return ClaudeProvider()
    raise ValueError(f"Unknown intelligence mode: {mode}")

