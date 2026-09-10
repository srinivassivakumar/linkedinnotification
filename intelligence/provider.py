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

    @abstractmethod
    def research_connection(
        self, connection: dict[str, Any], company_jobs: list[dict[str, Any]] | None = None
    ) -> dict[str, Any]:
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
    """Return the AI provider for ``mode``.

    Only the exact value ``"claude"`` selects the live Claude provider (which is
    the only path that could ever reach the Anthropic API). Every other value -
    ``"mock"``, ``"heuristic"``, ``""``, a typo - falls back to the deterministic
    ``MockProvider``. This makes an unattended cloud tick fail safe: it can never
    accidentally switch to Claude, and a misconfigured env var never crashes it.
    """
    normalized = (mode or "mock").strip().lower()
    if normalized == "claude":
        from intelligence.claude import ClaudeProvider

        return ClaudeProvider()
    if normalized in {"claude_cli", "claude-cli", "local", "cli"}:
        from intelligence.claude_cli import ClaudeCliProvider

        return ClaudeCliProvider()
    if normalized not in {"mock", "heuristic", "deterministic", "off", "none"}:
        print(f"intelligence: unknown CLAUDE_MODE {mode!r}; using deterministic MockProvider", flush=True)
    from intelligence.mock import MockProvider

    return MockProvider()

