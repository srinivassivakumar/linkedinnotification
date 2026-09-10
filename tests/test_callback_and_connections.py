from __future__ import annotations

from linkedin.connections import process_accepted_connection
from state.store import SqliteStore
from telegram.callback_worker import handle_callback


class FakeBot:
    configured = True

    def __init__(self):
        self.sent = []
        self.answers = []

    def answer_callback_query(self, cid, text=None):
        self.answers.append((cid, text))
        return {"ok": True}

    def send_message(self, text, reply_markup=None):
        self.sent.append(text)
        return {"ok": True}


class FakeProvider:
    def research_connection(self, connection, company_jobs=None):
        matched = company_jobs[0]["job_key"] if company_jobs else None
        return {
            "person_type": "employee",
            "company": connection.get("company") or "Acme",
            "matched_job_key": matched,
            "job_match_score": 75.0,
            "draft_kind": "referral" if matched else "networking",
            "draft_message": "Hi, great to connect.",
            "confidence": 0.7,
            "needs_human": True,
            "status": "awaiting_approval",
        }


PARSED = {
    "name": "Priya Sharma",
    "headline": "ML Engineer at Acme Cloud",
    "location": "India",
    "linkedin_profile_url": "https://www.linkedin.com/in/priya-sharma",
}


def test_connection_flow_and_gmail_idempotency(tmp_path):
    store = SqliteStore(tmp_path)
    conn1 = process_accepted_connection(PARSED, store, FakeProvider(), gmail_message_id="g1")
    conn2 = process_accepted_connection(PARSED, store, FakeProvider(), gmail_message_id="g1")
    assert conn1["id"] == conn2["id"]  # not reprocessed
    assert conn1["status"] == "awaiting_approval"
    assert conn1["person_type"] == "employee"


def test_callback_approve_is_idempotent(tmp_path):
    store = SqliteStore(tmp_path)
    conn = process_accepted_connection(PARSED, store, FakeProvider(), gmail_message_id="g1")
    bot = FakeProvider  # noqa: F841
    fb = FakeBot()
    first = handle_callback(f"conn:approve:{conn['id']}", "cb1", fb, store, None)
    second = handle_callback(f"conn:approve:{conn['id']}", "cb2", fb, store, None)
    assert first == "approved"
    assert second == "noop:approved"
    assert store.get_connection(conn["id"])["status"] == "approved"


def test_callback_job_skip_and_why(tmp_path):
    from orchestrator.models import Candidate, Job, ScoreResult

    store = SqliteStore(tmp_path)
    cand = Candidate(
        job=Job(source="greenhouse", source_job_id="123", company="Acme", title="MLE", url="https://x"),
        score=ScoreResult(pre_score=70, bucket="strong_candidate", signals={"freshness": 15, "evidence_overlap": 20}),
    )
    store.persist([cand])
    fb = FakeBot()
    assert handle_callback("skip:greenhouse:123", "c1", fb, store, None) == "skipped"
    assert handle_callback("why:greenhouse:123", "c2", fb, store, None) == "explained"
    assert any("WHY" in s for s in fb.sent)
