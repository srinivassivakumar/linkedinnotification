from __future__ import annotations

from orchestrator.models import Candidate, Job, ScoreResult
from state.store import SqliteStore


def _candidate(score: int = 70) -> Candidate:
    return Candidate(
        job=Job(source="fixture", source_job_id="1", company="Acme", title="DevOps Engineer", url="https://example.com"),
        score=ScoreResult(pre_score=score, bucket="strong_candidate", signals={"freshness": 15}),
    )


def test_state_idempotency_and_change_detection(tmp_path) -> None:
    store = SqliteStore(tmp_path)
    first = [_candidate(70)]
    assert store.diff_new_or_changed(first) == first
    store.persist(first)
    assert store.diff_new_or_changed(first) == []
    changed = [_candidate(72)]
    assert store.diff_new_or_changed(changed) == changed


def test_event_append(tmp_path) -> None:
    store = SqliteStore(tmp_path)
    event = store.append_event("test_event", "fixture:1", {"ok": True})
    assert event["type"] == "test_event"
    assert any(row["type"] == "test_event" for row in store.recent_events())


def test_processed_email_idempotency(tmp_path) -> None:
    store = SqliteStore(tmp_path)
    assert store.email_processed("m1") is False
    store.mark_email_processed("m1", kind="linkedin_acceptance")
    assert store.email_processed("m1") is True
    store.mark_email_processed("m1", kind="linkedin_acceptance")  # no error on repeat


def test_connection_round_trip(tmp_path) -> None:
    store = SqliteStore(tmp_path)
    cid = store.save_connection(
        {"name": "A B", "current_title": "ML Engineer @ Acme", "linkedin_url": "https://x"},
        gmail_message_id="g1",
    )
    store.update_connection_result(
        cid,
        {"person_type": "employee", "company": "Acme", "matched_job_key": "fixture:1",
         "draft_kind": "referral", "draft_message": "hi", "status": "awaiting_approval"},
    )
    row = store.get_connection(cid)
    assert row["company"] == "Acme" and row["status"] == "awaiting_approval"
    store.set_connection_status(cid, "approved")
    assert store.get_connection(cid)["status"] == "approved"
