from __future__ import annotations

import json
from types import SimpleNamespace

from intelligence.claude import ClaudeProvider
from intelligence.mock import MockProvider
from orchestrator.models import Job


class FakeClient:
    def __init__(self, payload):
        self._payload = payload
        self.calls = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        body = self._payload(kwargs) if callable(self._payload) else self._payload
        text = body if isinstance(body, str) else json.dumps(body)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)], stop_reason="end_turn")


def test_classify_reply_never_auto_replies_to_offers() -> None:
    provider = ClaudeProvider(client=FakeClient({
        "type": "offer", "company": "Acme", "role": "MLE",
        "confidence": 0.9, "recommended_action": "escalate", "needs_human": False,
    }))
    result = provider.classify_reply({"subject": "Your offer", "sender": "hr@acme.com", "snippet": "..."})
    assert result["type"] == "offer"
    assert result["needs_human"] is True


def test_classify_reply_falls_back_to_deterministic_on_error() -> None:
    def boom(_):
        raise RuntimeError("no api")

    provider = ClaudeProvider(client=FakeClient(boom))
    result = provider.classify_reply({"subject": "Thank you for applying", "sender": "x", "snippet": ""})
    assert result["type"] == "application_receipt"
    assert result["provider"] == "deterministic_fallback"


def test_tailor_application_drops_unverified_evidence() -> None:
    evidence = [{"id": "aws_backup_infrastructure", "title": "AWS S3 backup", "technologies": ["AWS"], "claims": []}]
    payload = {
        "base_track": "MLOps",
        "evidence_used": ["aws_backup_infrastructure: infra", "fake_evidence_x: invented"],
        "resume_markdown": "# Resume",
        "cover_letter": "Hi",
        "recruiter_email": "Hi",
        "referral_message": "Hi",
        "linkedin_message": "Hi",
        "application_answers": "## Q",
        "warnings": [],
    }
    provider = ClaudeProvider(client=FakeClient(payload))
    job = Job(source="fixture", source_job_id="1", company="Acme", title="MLOps Engineer", url="https://x")
    out = provider.tailor_application(job, evidence)
    assert out["status"] == "prepared"
    assert out["evidence_used"] == ["aws_backup_infrastructure: infra"]
    assert any("fake_evidence_x" in w for w in out["warnings"])
    assert set(out["files"]) >= {"resume.md", "cover_letter.md", "recruiter_email.txt", "application_answers.md"}


def test_research_connection_only_matches_provided_jobs() -> None:
    provider = ClaudeProvider(client=FakeClient({
        "person_type": "employee", "company": "Acme", "matched_job_key": "hallucinated:1",
        "job_match_score": 80, "draft_message": "hi", "confidence": 0.7,
    }))
    out = provider.research_connection({"name": "P", "headline": "MLE at Acme"}, [{"job_key": "real:1", "title": "MLE"}])
    assert out["matched_job_key"] is None  # hallucinated key rejected
    assert out["draft_kind"] == "networking"
    assert out["needs_human"] is True


def test_mock_provider_satisfies_full_interface() -> None:
    m = MockProvider()
    assert m.classify_reply({})["needs_human"] is True
    assert m.research_connection({"company": "X"})["status"] == "manual_review"
