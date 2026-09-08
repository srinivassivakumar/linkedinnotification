from __future__ import annotations

from orchestrator.models import Candidate, Job, ScoreResult
from state.store import JsonlStore


def _candidate(score: int = 70) -> Candidate:
    return Candidate(
        job=Job(source="fixture", source_job_id="1", company="Acme", title="DevOps Engineer", url="https://example.com"),
        score=ScoreResult(pre_score=score, bucket="strong_candidate", signals={"freshness": 15}),
    )


def test_state_idempotency_and_change_detection(tmp_path) -> None:
    store = JsonlStore(tmp_path)
    first = [_candidate(70)]
    assert store.diff_new_or_changed(first) == first
    store.persist(first)
    assert store.diff_new_or_changed(first) == []
    changed = [_candidate(72)]
    assert store.diff_new_or_changed(changed) == changed


def test_event_append(tmp_path) -> None:
    store = JsonlStore(tmp_path)
    event = store.append_event("test_event", "fixture:1", {"ok": True})
    assert event["type"] == "test_event"
    assert "test_event" in (tmp_path / "events.jsonl").read_text(encoding="utf-8")

