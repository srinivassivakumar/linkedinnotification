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
        return {
            "type": "unknown",
            "company": None,
            "role": None,
            "confidence": 0.0,
            "recommended_action": "manual_review",
            "needs_human": True,
            "provider": "mock",
        }

    def prepare_interview(self, application: dict[str, Any]) -> dict[str, Any]:
        return {"status": "mock", "provider": "mock"}

    def research_connection(
        self, connection: dict[str, Any], company_jobs: list[dict[str, Any]] | None = None
    ) -> dict[str, Any]:
        return {
            "person_type": "unknown",
            "company": connection.get("company"),
            "matched_job_key": None,
            "job_match_score": 0.0,
            "draft_kind": "networking",
            "draft_message": "Pending Claude drafting. Manual review required. LinkedIn sending is manual only.",
            "confidence": 0.0,
            "needs_human": True,
            "status": "manual_review",
            "provider": "mock",
        }

