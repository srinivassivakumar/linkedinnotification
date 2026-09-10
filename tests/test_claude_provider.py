from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from intelligence.claude import ClaudeProvider
from orchestrator.pipeline import (
    build_candidates,
    load_evidence,
    load_fixture,
    load_preferences,
    load_sources_config,
)

FIXTURE = Path("tests/fixtures/golden_jobs.json")


def _candidates():
    jobs = load_fixture(FIXTURE)
    candidates, _ = build_candidates(
        jobs, load_preferences(), load_evidence(), load_sources_config()
    )
    return candidates


class FakeClient:
    """Stands in for anthropic.Anthropic; records calls and returns canned JSON."""

    def __init__(self, payload):
        self._payload = payload
        self.calls: list[dict] = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        body = self._payload(kwargs) if callable(self._payload) else self._payload
        text = body if isinstance(body, str) else json.dumps(body)
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=text)],
            stop_reason="end_turn",
        )


GOOD = {
    "score": 82,
    "priority": "P1",
    "evidence_fit": ["aws_backup_infrastructure: Terraform + AWS S3 backup matches the infra ask"],
    "gaps": ["No verified Kubernetes platform ownership"],
    "risks": ["Location listed as hybrid; confirm Pune office"],
    "human_path_hint": "Reach the platform team lead; angle on Terraform/AWS backup work",
    "recommended_next_action": "prepare",
}


def test_only_serious_candidates_are_sent_to_claude():
    candidates = _candidates()
    fake = FakeClient(GOOD)
    provider = ClaudeProvider(client=fake)

    result = provider.evaluate_jobs(candidates, load_evidence())

    serious = [c for c in candidates if c.score.bucket in provider.evaluate_buckets]
    weak = [c for c in candidates if c.score.bucket not in provider.evaluate_buckets]
    assert len(fake.calls) == len(serious)
    assert serious, "fixture should contain at least one serious candidate"

    by_key = {c.job_key: c for c in result}
    for c in weak:
        assert by_key[c.job_key].intelligence["verdict"] == "not_evaluated"
    for c in serious:
        assert by_key[c.job_key].intelligence["verdict"] == "evaluated"


def test_structured_output_has_all_required_fields():
    candidates = _candidates()
    provider = ClaudeProvider(client=FakeClient(GOOD))
    evaluated = [
        c
        for c in provider.evaluate_jobs(candidates, load_evidence())
        if c.intelligence["verdict"] == "evaluated"
    ]
    assert evaluated
    intel = evaluated[0].intelligence
    for key in (
        "score",
        "priority",
        "evidence_fit",
        "gaps",
        "risks",
        "human_path_hint",
        "recommended_next_action",
    ):
        assert key in intel
    assert intel["priority"] in {"P0", "P1", "P2"}
    assert isinstance(intel["score"], int)
    assert intel["recommended_next_action"] in {"act_now", "prepare", "store", "archive"}


def test_unverified_evidence_ids_are_dropped_and_flagged():
    bad_fit = dict(GOOD)
    bad_fit["evidence_fit"] = [
        "totally_made_up_project: invented fit",
        "aws_backup_infrastructure: real verified fit",
    ]
    provider = ClaudeProvider(client=FakeClient(bad_fit))
    evaluated = [
        c
        for c in provider.evaluate_jobs(_candidates(), load_evidence())
        if c.intelligence["verdict"] == "evaluated"
    ]
    intel = evaluated[0].intelligence
    assert intel["evidence_fit"] == ["aws_backup_infrastructure: real verified fit"]
    assert any("totally_made_up_project" in w for w in intel["warnings"])


def test_malformed_response_keeps_job_for_human_review():
    provider = ClaudeProvider(client=FakeClient("not json at all"))
    result = provider.evaluate_jobs(_candidates(), load_evidence())
    errored = [c for c in result if c.intelligence["verdict"] == "error"]
    assert errored
    assert all(c.intelligence["needs_human"] for c in errored)


def test_transport_failure_is_surfaced_not_swallowed():
    def boom(_kwargs):
        raise RuntimeError("network down")

    provider = ClaudeProvider(client=FakeClient(boom))
    result = provider.evaluate_jobs(_candidates(), load_evidence())
    errored = [c for c in result if c.intelligence["verdict"] == "error"]
    assert errored
    assert "claude_call_failed" in errored[0].intelligence["error"]


def test_max_evaluations_cap_defers_remaining_candidates():
    candidates = _candidates()
    provider = ClaudeProvider(client=FakeClient(GOOD), max_evaluations=1)
    result = provider.evaluate_jobs(candidates, load_evidence())
    verdicts = [c.intelligence["verdict"] for c in result]
    assert verdicts.count("evaluated") == 1
    assert "not_evaluated" in verdicts


def test_provider_construction_does_not_require_api_key():
    # Must not raise even with no client and no ANTHROPIC_API_KEY.
    ClaudeProvider()
