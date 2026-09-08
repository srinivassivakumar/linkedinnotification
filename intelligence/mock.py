from __future__ import annotations

from typing import Any

from intelligence.provider import IntelligenceProvider
from orchestrator.models import Candidate, Job


class MockProvider(IntelligenceProvider):
    def evaluate_jobs(self, candidates: list[Candidate], evidence: list[dict[str, Any]]) -> list[Candidate]:
        output: list[Candidate] = []
        for candidate in candidates:
            priority = "P1" if candidate.score.pre_score >= 65 else "P2"
            updated = candidate.model_copy(deep=True)
            updated.intelligence = {
                "provider": "mock",
                "verdict": "mock_review",
                "priority": priority,
                "reason": "Mock provider - replace with Claude later",
            }
            output.append(updated)
        return output

    def tailor_application(self, job: Job, evidence: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "status": "mock",
            "files": {
                "resume.md": "Pending Claude tailoring. Do not submit this placeholder.",
                "recruiter_email.txt": "Pending Claude drafting. Manual review required.",
                "referral_message.txt": "Pending Claude drafting. Manual review required.",
                "linkedin_message.txt": "Pending Claude drafting. LinkedIn sending is manual only.",
            },
        }

    def classify_reply(self, message: Any) -> dict[str, Any]:
        return {"type": "unknown", "confidence": 0.0, "provider": "mock"}

    def prepare_interview(self, application: dict[str, Any]) -> dict[str, Any]:
        return {"status": "mock", "provider": "mock"}

