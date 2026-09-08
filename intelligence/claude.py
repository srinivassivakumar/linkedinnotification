from __future__ import annotations

from typing import Any

from intelligence.provider import IntelligenceProvider
from orchestrator.models import Candidate, Job


class ClaudeProvider(IntelligenceProvider):
    def __init__(self) -> None:
        raise RuntimeError("Claude provider is not configured yet. Keep CLAUDE_MODE=mock until Claude Pro setup is complete.")

    def evaluate_jobs(self, candidates: list[Candidate], evidence: list[dict[str, Any]]) -> list[Candidate]:
        raise NotImplementedError

    def tailor_application(self, job: Job, evidence: list[dict[str, Any]]) -> dict[str, Any]:
        raise NotImplementedError

    def classify_reply(self, message: Any) -> dict[str, Any]:
        raise NotImplementedError

    def prepare_interview(self, application: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

